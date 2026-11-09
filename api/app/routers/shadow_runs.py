from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import current_user, require_write
from app.models import Conversion, ShadowRun, User
from app.schemas import ShadowRunCreate, ShadowRunResponse
from app.services.conversion import load_mapping_metadata
from app.services.shadow_fixtures import get_fixture
from app.worker.tasks import shadow_run_task

router = APIRouter(tags=["Shadow Runs"])


async def _owned_conversion(db: AsyncSession, conversion_id: int, user: User) -> Conversion | None:
    conversion = await db.get(Conversion, conversion_id)
    mapping = await load_mapping_metadata(db, conversion.mapping_id) if conversion else None
    return conversion if mapping is not None and mapping.project.owner_id == user.id else None


@router.post("/conversions/{conversion_id}/shadow-runs", response_model=ShadowRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_shadow_run(conversion_id: int, body: ShadowRunCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    require_write(user)
    conversion = await _owned_conversion(db, conversion_id, user)
    if conversion is None:
        raise HTTPException(status_code=404, detail="Conversion not found")
    if get_fixture(body.fixture_id) is None:
        raise HTTPException(status_code=422, detail="Unsupported shadow fixture")
    mapping = await load_mapping_metadata(db, conversion.mapping_id)
    run = ShadowRun(project_id=mapping.project_id, mapping_id=mapping.id, conversion_id=conversion.id, owner_id=user.id, fixture_id=body.fixture_id)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    try:
        shadow_run_task.delay(run.id)
    except Exception:
        run.status = "failed"
        run.error = "queue_unavailable: Shadow run could not be queued"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=503, detail="Shadow run queue is unavailable")
    return run


@router.get("/shadow-runs/{shadow_run_id}", response_model=ShadowRunResponse)
async def get_shadow_run(shadow_run_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    run = await db.get(ShadowRun, shadow_run_id)
    if run is None or run.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    return run


@router.get("/conversions/{conversion_id}/shadow-runs", response_model=list[ShadowRunResponse])
async def list_shadow_runs(conversion_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if await _owned_conversion(db, conversion_id, user) is None:
        raise HTTPException(status_code=404, detail="Conversion not found")
    return list(await db.scalars(select(ShadowRun).where(ShadowRun.conversion_id == conversion_id).order_by(ShadowRun.created_at.desc(), ShadowRun.id.desc())))
