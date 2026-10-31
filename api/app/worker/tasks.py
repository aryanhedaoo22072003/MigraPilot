import asyncio

from app.database import SessionLocal, engine
from app.services.parse_upload import parse_and_persist_upload
from app.worker.celery_app import celery_app


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
