"""Create a corrected immutable conversion and PASS run in the isolated Phase 6 demo project."""
import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.cli.seed_phase6a_fail_demo import MAPPING_NAME, PROJECT_NAME
from app.core.config import settings
from app.database import SessionLocal, engine
from app.models import Conversion, Mapping, Project, ShadowRun, User
from app.services.shadow_execution import ShadowExecutionError, execute_and_compare
from app.services.shadow_fixtures import ORDERS_DISCOUNT_V1

CORRECTED_SQL = """with src_orders as (
  select order_id, amount from {{ source('raw', 'src_orders') }}
), exp_net as (
  select order_id, amount * 0.90 as net_amount from src_orders
), fil_positive as (
  select order_id, net_amount from exp_net where net_amount > 0
)
select order_id, net_amount from fil_positive"""


async def seed(owner_email: str) -> None:
    if not settings.shadow_loader_url or not settings.shadow_executor_url:
        raise SystemExit("Run this command in the worker container; the isolated shadow database is not configured.")
    async with SessionLocal() as db:
        owner = await db.scalar(select(User).where(User.email == owner_email.strip().lower()))
        if owner is None:
            raise SystemExit("The requested local owner account does not exist.")
        project = await db.scalar(select(Project).where(Project.owner_id == owner.id, Project.name == PROJECT_NAME))
        mapping = await db.scalar(select(Mapping).where(Mapping.project_id == project.id, Mapping.name == MAPPING_NAME)) if project else None
        if mapping is None:
            raise SystemExit("Run seed_phase6a_fail_demo first; no isolated FAIL demonstration mapping exists.")
        original = await db.scalar(select(Conversion).where(Conversion.mapping_id == mapping.id, Conversion.version == 1))
        if original is None:
            raise SystemExit("The isolated demonstration has no original failed conversion.")
        failed_run = await db.scalar(select(ShadowRun).where(
            ShadowRun.mapping_id == mapping.id,
            ShadowRun.conversion_id == original.id,
            ShadowRun.status == "completed", ShadowRun.comparison_result == "FAIL",
        ).order_by(ShadowRun.id.desc()))
        if failed_run is None:
            raise SystemExit("The isolated demonstration has no completed FAIL provenance to correct.")
        corrected = await db.scalar(select(Conversion).where(
            Conversion.mapping_id == mapping.id, Conversion.generated_sql == CORRECTED_SQL,
        ))
        if corrected is None:
            version = (await db.scalar(select(func.max(Conversion.version)).where(Conversion.mapping_id == mapping.id)) or 0) + 1
            corrected = Conversion(
                mapping_id=mapping.id, version=version, generated_sql=CORRECTED_SQL,
                schema_yml="version: 2\nmodels:\n  - name: m_orders_intentional_discount_mismatch\n",
                confidence=100, confidence_reasons=["Deterministic development correction, not AI-generated."],
                risk_flags=[], model_used="deterministic-dev-correction",
            )
            db.add(corrected); await db.flush()
        run = ShadowRun(
            project_id=project.id, mapping_id=mapping.id, conversion_id=corrected.id,
            owner_id=owner.id, fixture_id=ORDERS_DISCOUNT_V1.fixture_id,
            status="running", started_at=datetime.now(timezone.utc),
        )
        db.add(run); await db.commit(); await db.refresh(run)
        try:
            result = await asyncio.wait_for(
                execute_and_compare(run.id, corrected.generated_sql, ORDERS_DISCOUNT_V1),
                timeout=settings.shadow_job_timeout_seconds,
            )
            for key, value in result.items():
                setattr(run, key, value)
            run.status = "completed"
        except (ShadowExecutionError, TimeoutError) as exc:
            run.status = "failed"
            run.error = f"{getattr(exc, 'code', 'execution_timeout')}: Development correction validation failed safely"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        print(f"project_id={project.id}")
        print(f"mapping_id={mapping.id}")
        print(f"original_failed_conversion_id={original.id}")
        print(f"original_failed_shadow_run_id={failed_run.id}")
        print(f"corrected_conversion_id={corrected.id}")
        print(f"corrected_conversion_version={corrected.version}")
        print(f"passing_shadow_run_id={run.id}")
        print(f"status={run.status}")
        print(f"comparison_result={run.comparison_result or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--confirm-development-only", action="store_true")
    args = parser.parse_args()
    if not args.confirm_development_only:
        raise SystemExit("Refusing to create development PASS evidence without --confirm-development-only")
    try:
        asyncio.run(seed(args.owner_email))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
