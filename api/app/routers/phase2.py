import io
import stat
import zipfile
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.database import get_db
from app.deps import current_user, owned_project, require_write
from app.models import Job, Mapping, Transformation, Upload, User
from app.schemas import (
    JobResponse, LineageEdgeResponse, MappingDetailResponse, MappingSummaryResponse,
    UploadBatchResponse, UploadItemResponse,
)
from app.services.parse_upload import parse_and_persist_upload
from app.services.powercenter_parser import PowerCenterParseError, parse_powercenter_xml
from app.worker.tasks import parse_upload_task

router = APIRouter(tags=["PowerCenter Parser"])


async def _read_limited(file: UploadFile) -> bytes:
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"Upload exceeds {settings.max_upload_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


def _validate_xml(name: str, content: bytes) -> tuple[str, str]:
    if not name.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail=f"Only XML files are allowed inside ZIP archives: {name}")
    try:
        text = content.decode("utf-8-sig")
        parse_powercenter_xml(text)
    except (UnicodeDecodeError, PowerCenterParseError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid PowerCenter XML in {name}: {exc}") from exc
    return PurePosixPath(name).name, text


def _xml_documents(file_name: str, body: bytes) -> list[tuple[str, str]]:
    lower_name = file_name.lower()
    if lower_name.endswith(".xml"):
        return [_validate_xml(PurePosixPath(file_name).name, body)]
    if not lower_name.endswith(".zip"):
        raise HTTPException(status_code=415, detail="Upload must be a .xml or .zip file")
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        bad_member = archive.testzip()
        if bad_member:
            raise HTTPException(status_code=422, detail=f"Corrupt ZIP member: {bad_member}")
        members = [item for item in archive.infolist() if not item.is_dir()]
        if not members:
            raise HTTPException(status_code=422, detail="ZIP archive is empty")
        if len(members) > settings.max_zip_files:
            raise HTTPException(status_code=413, detail="ZIP contains too many files")
        total = 0
        documents = []
        for member in members:
            path = PurePosixPath(member.filename.replace("\\", "/"))
            mode = member.external_attr >> 16
            if path.is_absolute() or ".." in path.parts or stat.S_ISLNK(mode):
                raise HTTPException(status_code=422, detail=f"Unsafe ZIP path: {member.filename}")
            total += member.file_size
            if total > settings.max_zip_uncompressed_bytes:
                raise HTTPException(status_code=413, detail="ZIP extracted content is too large")
            if member.compress_size == 0 and member.file_size > 0 or (
                member.compress_size and member.file_size / member.compress_size > 100
            ):
                raise HTTPException(status_code=413, detail=f"Suspicious ZIP compression ratio: {member.filename}")
            documents.append(_validate_xml(member.filename, archive.read(member)))
        return documents
    except HTTPException:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid ZIP archive") from exc


@router.post("/projects/{project_id}/uploads", response_model=UploadBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_upload(
    project_id: int, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    require_write(user)
    await owned_project(db, project_id, user)
    documents = _xml_documents(file.filename or "upload", await _read_limited(file))
    queued: list[tuple[Upload, Job]] = []
    for name, text in documents:
        upload = Upload(project_id=project_id, file_name=name, raw_xml=text, status="uploaded")
        db.add(upload)
        await db.flush()
        job = Job(project_id=project_id, upload_id=upload.id, type="parse", status="queued", progress=0)
        db.add(job)
        await db.flush()
        queued.append((upload, job))
    await db.commit()
    for upload, job in queued:
        if settings.parse_tasks_eager:
            await parse_and_persist_upload(db, upload.id, job.id)
        else:
            parse_upload_task.delay(upload.id, job.id)
    return UploadBatchResponse(uploads=[
        UploadItemResponse(id=upload.id, file_name=upload.file_name, status=upload.status, job_id=job.id)
        for upload, job in queued
    ])


@router.get("/projects/{project_id}/mappings", response_model=list[MappingSummaryResponse])
async def list_mappings(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    await owned_project(db, project_id, user)
    return (await db.scalars(select(Mapping).where(Mapping.project_id == project_id).order_by(Mapping.id))).all()


@router.get("/mappings/{mapping_id}", response_model=MappingDetailResponse)
async def get_mapping(mapping_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    mapping = await db.scalar(
        select(Mapping).where(Mapping.id == mapping_id).options(
            selectinload(Mapping.project), selectinload(Mapping.transformations).selectinload(Transformation.ports),
            selectinload(Mapping.lineage_edges),
        )
    )
    if mapping is None or mapping.project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mapping not found")
    ports = {port.id: (transform.name, port.name) for transform in mapping.transformations for port in transform.ports}
    edge_responses = [LineageEdgeResponse(
        id=edge.id, from_port_id=edge.from_port_id, to_port_id=edge.to_port_id,
        from_transformation=ports[edge.from_port_id][0], from_port=ports[edge.from_port_id][1],
        to_transformation=ports[edge.to_port_id][0], to_port=ports[edge.to_port_id][1],
    ) for edge in mapping.lineage_edges]
    base = MappingSummaryResponse.model_validate(mapping)
    return MappingDetailResponse(
        **base.model_dump(), transformations=mapping.transformations, lineage_edges=edge_responses
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    job = await db.get(Job, job_id)
    if job is None or job.project_id is None:
        raise HTTPException(status_code=404, detail="Job not found")
    await owned_project(db, job.project_id, user)
    return job
