"""Phase 5A shadow-run comparison persistence."""
from alembic import op
import sqlalchemy as sa

revision = "0004_phase5a_shadow_runs"
down_revision = "0003_conversion_reasons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("shadow_runs_status_check", "shadow_runs", type_="check")
    op.add_column("shadow_runs", sa.Column("project_id", sa.BigInteger(), nullable=True))
    op.add_column("shadow_runs", sa.Column("mapping_id", sa.BigInteger(), nullable=True))
    op.add_column("shadow_runs", sa.Column("owner_id", sa.BigInteger(), nullable=True))
    op.add_column("shadow_runs", sa.Column("fixture_id", sa.String(100), nullable=False, server_default="orders_discount_v1"))
    op.add_column("shadow_runs", sa.Column("comparison_result", sa.String(10)))
    for name in ("reference_row_count", "migrated_row_count", "matched_rows", "missing_rows", "unexpected_rows", "duplicate_key_mismatches", "column_mismatches", "null_mismatches", "numeric_precision_differences", "execution_time_ms"):
        op.add_column("shadow_runs", sa.Column(name, sa.Integer()))
    op.add_column("shadow_runs", sa.Column("mismatch_samples", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("shadow_runs", sa.Column("error", sa.Text()))
    op.add_column("shadow_runs", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("shadow_runs", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.execute("""UPDATE shadow_runs sr SET mapping_id=c.mapping_id, project_id=m.project_id, owner_id=p.owner_id FROM conversions c JOIN mappings m ON m.id=c.mapping_id JOIN projects p ON p.id=m.project_id WHERE c.id=sr.conversion_id""")
    for name in ("project_id", "mapping_id", "owner_id"):
        op.alter_column("shadow_runs", name, nullable=False)
    op.alter_column("shadow_runs", "legacy_table", nullable=True)
    op.alter_column("shadow_runs", "new_table", nullable=True)
    op.alter_column("shadow_runs", "pk_columns", nullable=True)
    op.alter_column("shadow_runs", "status", server_default="queued")
    op.create_check_constraint("ck_shadow_runs_status", "shadow_runs", "status IN ('queued','running','completed','failed')")
    op.create_check_constraint("ck_shadow_runs_result", "shadow_runs", "comparison_result IS NULL OR comparison_result IN ('PASS','FAIL')")
    op.create_foreign_key("fk_shadow_runs_project", "shadow_runs", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_shadow_runs_mapping", "shadow_runs", "mappings", ["mapping_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_shadow_runs_owner", "shadow_runs", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_index("idx_shadow_runs_conversion_created", "shadow_runs", ["conversion_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_shadow_runs_conversion_created", table_name="shadow_runs")
    for constraint in ("fk_shadow_runs_owner", "fk_shadow_runs_mapping", "fk_shadow_runs_project", "ck_shadow_runs_result", "ck_shadow_runs_status"):
        op.drop_constraint(constraint, "shadow_runs", type_="foreignkey" if constraint.startswith("fk_") else "check")
    for name in ("completed_at", "created_at", "error", "mismatch_samples", "execution_time_ms", "numeric_precision_differences", "null_mismatches", "column_mismatches", "duplicate_key_mismatches", "unexpected_rows", "missing_rows", "matched_rows", "migrated_row_count", "reference_row_count", "comparison_result", "fixture_id", "owner_id", "mapping_id", "project_id"):
        op.drop_column("shadow_runs", name)
    op.alter_column("shadow_runs", "legacy_table", nullable=False)
    op.alter_column("shadow_runs", "new_table", nullable=False)
    op.alter_column("shadow_runs", "pk_columns", nullable=False)
    op.create_check_constraint("shadow_runs_status_check", "shadow_runs", "status IN ('queued','running','passed','failed','error')")
