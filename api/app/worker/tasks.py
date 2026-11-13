import asyncio
from datetime import datetime, timezone
import logging

from billiard.exceptions import SoftTimeLimitExceeded

from app.database import SessionLocal, engine
from app.core.config import settings
from app.services.parse_upload import parse_and_persist_upload
from app.models import Conversion, ShadowRun
from app.services.shadow_execution import ShadowExecutionError, ShadowTimeout, execute_and_compare
from app.services.shadow_fixtures import get_fixture
from app.ai_service import AIService
from app.services.autopsy import persist_autopsy_failure, process_autopsy
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="migrapilot.parse_upload")
def parse_upload_task(upload_id: int, job_id: int) -> None:
    async def run() -> None:
        try:
            async with SessionLocal() as db:
                await parse_and_persist_upload(db, upload_id, job_id)
        finally:
            # Celery invokes asyncio.run per task; discard loop-bound asyncpg connections.
            await engine.dispose()

    asyncio.run(run())


@celery_app.task(name="migrapilot.shadow_run", soft_time_limit=settings.shadow_job_timeout_seconds + 5, time_limit=settings.shadow_job_timeout_seconds + 10)
def shadow_run_task(shadow_run_id: int) -> None:
    async def run() -> None:
        try:
            async with SessionLocal() as db:
                shadow_run = await db.get(ShadowRun, shadow_run_id)
                if shadow_run is None or shadow_run.status == "completed":
                    return
                shadow_run.status = "running"
                shadow_run.started_at = datetime.now(timezone.utc)
                shadow_run.error = None
                await db.commit()
                try:
                    conversion = await db.get(Conversion, shadow_run.conversion_id)
                    fixture = get_fixture(shadow_run.fixture_id)
                    if conversion is None or fixture is None:
                        raise ShadowExecutionError("Required conversion or fixture is unavailable")
                    try:
                        result = await asyncio.wait_for(execute_and_compare(shadow_run.id, conversion.generated_sql, fixture), timeout=settings.shadow_job_timeout_seconds)
                    except TimeoutError as exc:
                        raise ShadowTimeout("Shadow job exceeded its total time limit") from exc
                    for key, value in result.items():
                        setattr(shadow_run, key, value)
                    shadow_run.status = "completed"
                except ShadowExecutionError as exc:
                    shadow_run.status = "failed"
                    shadow_run.error = f"{exc.code}: {str(exc)[:240]}"
                except Exception:
                    shadow_run.status = "failed"
                    shadow_run.error = "internal_error: Shadow execution failed safely"
                shadow_run.completed_at = datetime.now(timezone.utc)
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


async def _run_autopsy_once(autopsy_id: int) -> None:
    ai_service = AIService.from_settings()
    try:
        async with SessionLocal() as db:
            await process_autopsy(db, autopsy_id, ai_service)
    finally:
        try:
            await asyncio.wait_for(ai_service.aclose(), timeout=5)
        except Exception:
            logger.warning("autopsy_provider_cleanup_failed autopsy_id=%s", autopsy_id)
        await engine.dispose()


async def _record_autopsy_soft_timeout(autopsy_id: int) -> None:
    # The interrupted loop may have held a checked-out connection. Dispose the
    # pool first, then use a new session/transaction solely for terminal state.
    await engine.dispose()
    async with SessionLocal() as db:
        await persist_autopsy_failure(db, autopsy_id, "task_soft_timeout")
    await engine.dispose()


def _run_autopsy_task_boundary(autopsy_id: int) -> None:
    try:
        asyncio.run(_run_autopsy_once(autopsy_id))
    except SoftTimeLimitExceeded:
        logger.warning("autopsy_task_soft_timeout autopsy_id=%s", autopsy_id)
        asyncio.run(_record_autopsy_soft_timeout(autopsy_id))


@celery_app.task(
    name="migrapilot.autopsy",
    soft_time_limit=settings.ai_autopsy_task_soft_limit_seconds,
    time_limit=settings.ai_autopsy_task_hard_limit_seconds,
)
def autopsy_task(autopsy_id: int) -> None:
    _run_autopsy_task_boundary(autopsy_id)
