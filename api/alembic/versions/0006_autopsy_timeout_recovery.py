"""Bounded Autopsy task tracking and stale-run recovery metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0006_autopsy_timeout_recovery"
down_revision = "0005_phase6a_ai_autopsy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("autopsies", sa.Column("celery_task_id", sa.String(50)))
    op.add_column("autopsies", sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
    op.create_index("uq_autopsies_celery_task_id", "autopsies", ["celery_task_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_autopsies_celery_task_id", table_name="autopsies")
    op.drop_column("autopsies", "heartbeat_at")
    op.drop_column("autopsies", "celery_task_id")
