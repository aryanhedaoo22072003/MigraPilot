"""Recover confirmed stale running Autopsies after inspecting live Celery workers."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import re

from app.core.config import settings
from app.database import SessionLocal, engine
from app.services.autopsy import recover_stale_running_autopsies
from app.worker.celery_app import celery_app


def _live_autopsy_work() -> tuple[set[str], set[int]]:
    inspector = celery_app.control.inspect(timeout=5)
    snapshots = [inspector.active(), inspector.reserved(), inspector.scheduled()]
    if any(snapshot is None for snapshot in snapshots):
        raise SystemExit("Celery inspection did not receive a worker response; refusing recovery.")
    task_ids: set[str] = set()
    autopsy_ids: set[int] = set()
    for snapshot in snapshots:
        for tasks in snapshot.values():
            for item in tasks:
                request = item.get("request", item)
                if request.get("name") != "migrapilot.autopsy":
                    continue
                if request.get("id"):
                    task_ids.add(str(request["id"]))
                args = request.get("args", [])
                if isinstance(args, (list, tuple)) and args:
                    try:
                        autopsy_ids.add(int(args[0]))
                    except (TypeError, ValueError):
                        pass
                elif isinstance(args, str):
                    match = re.search(r"\d+", args)
                    if match:
                        autopsy_ids.add(int(match.group()))
    return task_ids, autopsy_ids


async def recover(autopsy_id: int, category: str) -> list[int]:
    try:
        active_task_ids, active_autopsy_ids = _live_autopsy_work()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.ai_autopsy_stale_after_seconds)
        async with SessionLocal() as db:
            return await recover_stale_running_autopsies(
                db, cutoff=cutoff, active_task_ids=active_task_ids,
                active_autopsy_ids=active_autopsy_ids, autopsy_id=autopsy_id,
                category=category,
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--autopsy-id", type=int, required=True)
    parser.add_argument(
        "--reason", choices=("task_soft_timeout", "worker_interrupted_stale"),
        default="worker_interrupted_stale",
    )
    parser.add_argument("--confirm-stale-recovery", action="store_true")
    args = parser.parse_args()
    if not args.confirm_stale_recovery:
        raise SystemExit("Refusing recovery without --confirm-stale-recovery")
    recovered = asyncio.run(recover(args.autopsy_id, args.reason))
    if recovered != [args.autopsy_id]:
        raise SystemExit("No record recovered: it is absent, terminal, not stale, or still active.")
    print(f"Recovered Autopsy {args.autopsy_id} as failed ({args.reason}).")


if __name__ == "__main__":
    main()
