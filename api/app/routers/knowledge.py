from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import current_user, owned_project, require_write
from app.models import Autopsy, Conversion, KnowledgeCandidate, User
from app.schemas import (
    KnowledgeCandidateListResponse, KnowledgeCandidateResponse, KnowledgeReviewRequest,
    KnowledgeStatus, KnowledgeSuggestionResponse, KnowledgeVerificationRequest,
)
from app.services.conversion import load_mapping_metadata
from app.services.knowledge import (
    KnowledgeValidationError, create_candidate, load_candidate, review_candidate,
    score_candidate, verify_candidate,
)

router = APIRouter(tags=["Failure Knowledge Base"])


async def _owned_candidate(db: AsyncSession, candidate_id: int, user: User) -> KnowledgeCandidate | None:
    candidate = await load_candidate(db, candidate_id)
    return candidate if candidate is not None and candidate.owner_id == user.id else None


def _validation_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/autopsies/{autopsy_id}/knowledge-candidates",
    response_model=KnowledgeCandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_candidate(
    autopsy_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    require_write(user)
    autopsy = await db.get(Autopsy, autopsy_id)
    if autopsy is None or autopsy.owner_id != user.id:
        raise HTTPException(status_code=404, detail="AI Autopsy not found")
    duplicate = await db.scalar(select(KnowledgeCandidate).where(
        KnowledgeCandidate.project_id == autopsy.project_id,
        KnowledgeCandidate.source_autopsy_id == autopsy.id,
    ))
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A knowledge candidate already exists for this AI Autopsy")
    try:
        return await create_candidate(db, autopsy, user.id)
    except (KnowledgeValidationError, ValidationError) as exc:
        await db.rollback()
        raise _validation_error(exc) from exc
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A knowledge candidate already exists for this AI Autopsy") from exc


@router.get("/projects/{project_id}/knowledge-candidates", response_model=KnowledgeCandidateListResponse)
async def list_knowledge_candidates(
    project_id: int,
    candidate_status: KnowledgeStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100_000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    await owned_project(db, project_id, user)
    filters = [KnowledgeCandidate.project_id == project_id, KnowledgeCandidate.owner_id == user.id]
    if candidate_status:
        filters.append(KnowledgeCandidate.status == candidate_status)
    total = await db.scalar(select(func.count(KnowledgeCandidate.id)).where(*filters)) or 0
    ids = list(await db.scalars(
        select(KnowledgeCandidate.id).where(*filters)
        .order_by(KnowledgeCandidate.created_at.desc(), KnowledgeCandidate.id.desc())
        .limit(limit).offset(offset)
    ))
    items = [await load_candidate(db, candidate_id) for candidate_id in ids]
    return KnowledgeCandidateListResponse(items=[item for item in items if item], total=total, limit=limit, offset=offset)


@router.get("/knowledge-candidates/{candidate_id}", response_model=KnowledgeCandidateResponse)
async def get_knowledge_candidate(
    candidate_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    candidate = await _owned_candidate(db, candidate_id, user)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found")
    return candidate


@router.post("/knowledge-candidates/{candidate_id}/verification", response_model=KnowledgeCandidateResponse)
async def attach_knowledge_verification(
    candidate_id: int,
    body: KnowledgeVerificationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    require_write(user)
    candidate = await _owned_candidate(db, candidate_id, user)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found")
    from app.models import ShadowRun
    passing_run = await db.get(ShadowRun, body.passing_shadow_run_id)
    if passing_run is None or passing_run.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    try:
        return await verify_candidate(db, candidate, passing_run, user.id)
    except KnowledgeValidationError as exc:
        await db.rollback()
        raise _validation_error(exc) from exc


@router.post("/knowledge-candidates/{candidate_id}/review", response_model=KnowledgeCandidateResponse)
async def review_knowledge_candidate(
    candidate_id: int,
    body: KnowledgeReviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    require_write(user)
    candidate = await _owned_candidate(db, candidate_id, user)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Knowledge candidate not found")
    try:
        return await review_candidate(db, candidate, body.decision, body.notes, user.id)
    except KnowledgeValidationError as exc:
        await db.rollback()
        raise _validation_error(exc) from exc


@router.get("/mappings/{mapping_id}/knowledge-suggestions", response_model=list[KnowledgeSuggestionResponse])
async def knowledge_suggestions(
    mapping_id: int,
    conversion_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=10, ge=1, le=25),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    mapping = await load_mapping_metadata(db, mapping_id)
    if mapping is None or mapping.project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Mapping not found")
    conversion = None
    if conversion_id is not None:
        conversion = await db.get(Conversion, conversion_id)
        if conversion is None or conversion.mapping_id != mapping.id:
            raise HTTPException(status_code=404, detail="Conversion not found")
    candidates = list(await db.scalars(select(KnowledgeCandidate).where(
        KnowledgeCandidate.project_id == mapping.project_id,
        KnowledgeCandidate.owner_id == user.id,
        KnowledgeCandidate.status == "published",
    )))
    ranked = []
    for candidate in candidates:
        score, reasons = score_candidate(candidate, mapping, conversion)
        if score <= 0 or not candidate.verified_remediation_summary or not candidate.corrected_conversion_version or not candidate.published_at:
            continue
        relevance = "HIGH" if score >= 6 else "MEDIUM" if score >= 3 else "LOW"
        ranked.append((score, candidate.published_at, KnowledgeSuggestionResponse(
            knowledge_id=candidate.id, diagnosis_category=candidate.diagnosis_category,
            relevance=relevance, reasons=reasons,
            root_cause_summary=candidate.root_cause_summary,
            suggested_corrective_actions=candidate.suggested_corrective_actions,
            verified_remediation_summary=candidate.verified_remediation_summary,
            fixture_id=candidate.fixture_id,
            corrected_conversion_version=candidate.corrected_conversion_version,
            published_at=candidate.published_at,
        )))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in ranked[:limit]]
