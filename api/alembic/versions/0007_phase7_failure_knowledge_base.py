"""Verified, project-scoped ETL failure knowledge lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = "0007_phase7_failure_knowledge_base"
down_revision = "0006_autopsy_timeout_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_candidates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("project_id", sa.BigInteger(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mapping_id", sa.BigInteger(), sa.ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_autopsy_id", sa.BigInteger(), sa.ForeignKey("autopsies.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_shadow_run_id", sa.BigInteger(), sa.ForeignKey("shadow_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_conversion_id", sa.BigInteger(), sa.ForeignKey("conversions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("corrected_conversion_id", sa.BigInteger(), sa.ForeignKey("conversions.id", ondelete="RESTRICT")),
        sa.Column("corrected_conversion_version", sa.Integer()),
        sa.Column("passing_shadow_run_id", sa.BigInteger(), sa.ForeignKey("shadow_runs.id", ondelete="RESTRICT")),
        sa.Column("diagnosis_category", sa.String(50), nullable=False),
        sa.Column("transformation_identifiers", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("affected_columns", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("signature_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("root_cause_summary", sa.Text(), nullable=False),
        sa.Column("suggested_corrective_actions", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("verified_remediation_summary", sa.Text()),
        sa.Column("fixture_id", sa.String(100), nullable=False),
        sa.Column("verification_outcome", sa.String(30)),
        sa.Column("verification_scope", sa.String(300)),
        sa.Column("verification_evidence", sa.JSON()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("reviewer_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("review_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','verified','published','rejected','archived')", name="ck_knowledge_candidates_status"),
        sa.CheckConstraint("verification_outcome IS NULL OR verification_outcome = 'PASS'", name="ck_knowledge_verification_outcome"),
        sa.UniqueConstraint("project_id", "source_autopsy_id", name="uq_knowledge_project_autopsy"),
    )
    op.create_index("idx_knowledge_project_status", "knowledge_candidates", ["project_id", "status", "created_at"])
    op.create_index("idx_knowledge_mapping", "knowledge_candidates", ["mapping_id"])
    op.create_index("idx_knowledge_category", "knowledge_candidates", ["project_id", "diagnosis_category"])
    op.create_table(
        "knowledge_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("candidate_id", sa.BigInteger(), sa.ForeignKey("knowledge_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(20)),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("evidence_snapshot", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_knowledge_events_candidate", "knowledge_events", ["candidate_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_knowledge_events_candidate", table_name="knowledge_events")
    op.drop_table("knowledge_events")
    op.drop_index("idx_knowledge_category", table_name="knowledge_candidates")
    op.drop_index("idx_knowledge_mapping", table_name="knowledge_candidates")
    op.drop_index("idx_knowledge_project_status", table_name="knowledge_candidates")
    op.drop_table("knowledge_candidates")
