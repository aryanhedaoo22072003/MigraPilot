from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, ai_autopsy_limiter
from app.database import get_db
from app.deps import current_user, require_write
from app.models import Autopsy, Project, ShadowRun, User
from app.schemas import AutopsyResponse
from app.services.autopsy import execution_error_category
from app.worker.tasks import autopsy_task

router = APIRouter(tags=["AI Autopsy"])


async def _owned_run(db: AsyncSession, shadow_run_id: int, user: User) -> ShadowRun | None:
    return await db.scalar(
        select(ShadowRun)
        .join(Project, Project.id == ShadowRun.project_id)
        .where(ShadowRun.id == shadow_run_id, ShadowRun.owner_id == user.id, Project.owner_id == user.id)
    )


async def _owned_autopsy(db: AsyncSession, autopsy_id: int, user: User) -> Autopsy | None:
    return await db.scalar(
        select(Autopsy)
        .join(Project, Project.id == Autopsy.project_id)
        .where(Autopsy.id == autopsy_id, Autopsy.owner_id == user.id, Project.owner_id == user.id)
    )


def _check_eligibility(run: ShadowRun) -> None:
    if run.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Shadow run is still processing")
    if run.status == "completed" and run.comparison_result == "PASS":
        raise HTTPException(status_code=422, detail="PASS shadow runs are not eligible for AI Autopsy")
    if run.status == "completed" and run.comparison_result == "FAIL":
        return
    if run.status == "failed" and execution_error_category(run.error):
        return
    raise HTTPException(status_code=422, detail="Shadow run has no diagnostic mismatch or sanitized execution failure evidence")


def _check_rate_limit(user: User) -> None:
    try:
        ai_autopsy_limiter.check(f"autopsy:user:{user.id}", settings.ai_autopsy_rate_limit_per_minute)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429, detail="AI Autopsy rate limit exceeded; retry later",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@router.post("/shadow-runs/{shadow_run_id}/autopsies", response_model=AutopsyResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_autopsy(
    shadow_run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    require_write(user)
    run = await _owned_run(db, shadow_run_id, user)
    if run is None:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    _check_eligibility(run)
    existing = await db.scalar(select(Autopsy).where(
        Autopsy.shadow_run_id == run.id,
        Autopsy.status.in_(("queued", "running")),
    ).order_by(Autopsy.id.desc()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An AI Autopsy is already processing for this shadow run")
    _check_rate_limit(user)
    autopsy = Autopsy(
        shadow_run_id=run.id, project_id=run.project_id, mapping_id=run.mapping_id,
        conversion_id=run.conversion_id, owner_id=user.id, celery_task_id=str(uuid4()),
    )
    db.add(autopsy)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="An AI Autopsy is already processing for this shadow run") from exc
    await db.refresh(autopsy)
    try:
        autopsy_task.apply_async(args=[autopsy.id], task_id=autopsy.celery_task_id)
    except Exception:
        autopsy.status = "failed"
        autopsy.provider_error = "queue_unavailable"
        autopsy.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(status_code=503, detail="AI Autopsy queue is unavailable")
    return autopsy


@router.get("/autopsies/{autopsy_id}", response_model=AutopsyResponse)
async def get_autopsy(
    autopsy_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    autopsy = await _owned_autopsy(db, autopsy_id, user)
    if autopsy is None:
        raise HTTPException(status_code=404, detail="AI Autopsy not found")
    return autopsy


@router.get("/shadow-runs/{shadow_run_id}/autopsies", response_model=list[AutopsyResponse])
async def list_autopsies(
    shadow_run_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    run = await _owned_run(db, shadow_run_id, user)
    if run is None:
        raise HTTPException(status_code=404, detail="Shadow run not found")
    return list(await db.scalars(select(Autopsy).where(
        Autopsy.shadow_run_id == run.id,
        Autopsy.owner_id == user.id,
    ).order_by(Autopsy.created_at.desc(), Autopsy.id.desc())))
