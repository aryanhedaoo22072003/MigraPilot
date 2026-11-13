"""Create and execute a deterministic Phase 6A FAIL demo in the isolated shadow DB."""
import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.database import SessionLocal, engine
from app.models import Conversion, LineageEdge, Mapping, Port, Project, ShadowRun, Transformation, User
from app.services.shadow_execution import ShadowExecutionError, execute_and_compare
from app.services.shadow_fixtures import ORDERS_DISCOUNT_V1

PROJECT_NAME = "Phase 6A AI Autopsy FAIL Demo"
MAPPING_NAME = "m_orders_intentional_discount_mismatch"
WRONG_SQL = """with src_orders as (
  select order_id, amount from {{ source('raw', 'src_orders') }}
), exp_net as (
  select order_id, amount * 0.80 as net_amount from src_orders
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
        if project is None:
            project = Project(owner_id=owner.id, name=PROJECT_NAME, source_system="powercenter", target_system="dbt_postgres")
            db.add(project)
            await db.flush()
        mapping = await db.scalar(select(Mapping).where(Mapping.project_id == project.id, Mapping.name == MAPPING_NAME))
        if mapping is None:
            mapping = Mapping(
                project_id=project.id, name=MAPPING_NAME,
                description_ai="Development-only deterministic mismatch: PowerCenter uses 0.90 while SQL uses 0.80.",
                status="converted",
            )
            db.add(mapping)
            await db.flush()
            source = Transformation(mapping_id=mapping.id, name="SRC_ORDERS", type="Source Definition", logic_json={}, seq_order=0)
            expression = Transformation(mapping_id=mapping.id, name="EXP_NET", type="Expression", logic_json={}, seq_order=1)
            target = Transformation(mapping_id=mapping.id, name="TGT_ORDERS", type="Target Definition", logic_json={}, seq_order=2)
            db.add_all([source, expression, target])
            await db.flush()
            src_amount = Port(transformation_id=source.id, name="AMOUNT", datatype="decimal", direction="OUT")
            exp_amount = Port(transformation_id=expression.id, name="AMOUNT", datatype="decimal", direction="IN")
            exp_net = Port(transformation_id=expression.id, name="NET_AMOUNT", datatype="decimal", direction="OUT", expression="AMOUNT * 0.90")
            tgt_net = Port(transformation_id=target.id, name="NET_AMOUNT", datatype="decimal", direction="IN")
            db.add_all([src_amount, exp_amount, exp_net, tgt_net])
            await db.flush()
            db.add_all([
                LineageEdge(mapping_id=mapping.id, from_port_id=src_amount.id, to_port_id=exp_amount.id),
                LineageEdge(mapping_id=mapping.id, from_port_id=exp_net.id, to_port_id=tgt_net.id),
            ])
        conversion = await db.scalar(select(Conversion).where(Conversion.mapping_id == mapping.id, Conversion.version == 1))
        if conversion is None:
            conversion = Conversion(
                mapping_id=mapping.id, version=1, generated_sql=WRONG_SQL,
                schema_yml="version: 2\nmodels:\n  - name: m_orders_intentional_discount_mismatch\n",
                confidence=10, confidence_reasons=["Intentionally incorrect development fixture."],
                risk_flags=[{"code": "INTENTIONAL_DEMO_MISMATCH", "severity": "high", "message": "Development-only 0.80 multiplier."}],
                model_used="deterministic-dev-seed",
            )
            db.add(conversion)
            await db.flush()
        run = ShadowRun(
            project_id=project.id, mapping_id=mapping.id, conversion_id=conversion.id,
            owner_id=owner.id, fixture_id=ORDERS_DISCOUNT_V1.fixture_id, status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        try:
            result = await asyncio.wait_for(
                execute_and_compare(run.id, conversion.generated_sql, ORDERS_DISCOUNT_V1),
                timeout=settings.shadow_job_timeout_seconds,
            )
            for key, value in result.items():
                setattr(run, key, value)
            run.status = "completed"
        except (ShadowExecutionError, TimeoutError) as exc:
            run.status = "failed"
            run.error = f"{getattr(exc, 'code', 'execution_timeout')}: Development demo execution failed safely"
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        print(f"project_id={project.id}")
        print(f"mapping_id={mapping.id}")
        print(f"conversion_id={conversion.id}")
        print(f"shadow_run_id={run.id}")
        print(f"status={run.status}")
        print(f"comparison_result={run.comparison_result or 'none'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--confirm-development-only", action="store_true")
    args = parser.parse_args()
    if not args.confirm_development_only:
        raise SystemExit("Refusing to seed without --confirm-development-only")
    try:
        asyncio.run(seed(args.owner_email))
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
