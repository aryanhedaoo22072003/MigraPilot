"""Persist structured confidence reasons for conversion versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_conversion_reasons"
down_revision = "0002_link_parse_jobs_to_uploads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversions",
        sa.Column(
            "confidence_reasons", postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversions", "confidence_reasons")
