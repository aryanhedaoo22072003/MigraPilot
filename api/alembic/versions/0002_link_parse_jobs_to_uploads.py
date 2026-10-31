"""Link background parse jobs to their source upload."""
from alembic import op
import sqlalchemy as sa

revision = "0002_link_parse_jobs_to_uploads"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("upload_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_upload_id_uploads", "jobs", "uploads", ["upload_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("idx_jobs_upload", "jobs", ["upload_id"])


def downgrade() -> None:
    op.drop_index("idx_jobs_upload", table_name="jobs")
    op.drop_constraint("fk_jobs_upload_id_uploads", "jobs", type_="foreignkey")
    op.drop_column("jobs", "upload_id")
