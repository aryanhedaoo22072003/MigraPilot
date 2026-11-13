"""Phase 6A persistent AI Autopsy lifecycle and structured diagnoses."""
from alembic import op
import sqlalchemy as sa

revision = "0005_phase6a_ai_autopsy"
down_revision = "0004_phase5a_shadow_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("autopsies_status_check", "autopsies", type_="check")
    op.alter_column("autopsies", "trigger_type", nullable=True)
    op.alter_column("autopsies", "root_cause", nullable=True)
    op.alter_column("autopsies", "status", server_default="queued")
    op.add_column("autopsies", sa.Column("project_id", sa.BigInteger()))
    op.add_column("autopsies", sa.Column("conversion_id", sa.BigInteger()))
    op.add_column("autopsies", sa.Column("owner_id", sa.BigInteger()))
    op.add_column("autopsies", sa.Column("diagnosis_category", sa.String(50)))
    op.add_column("autopsies", sa.Column("diagnosis_json", sa.JSON()))
    op.add_column("autopsies", sa.Column("suggested_corrections", sa.JSON(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("autopsies", sa.Column("suggested_sql", sa.Text()))
    op.add_column("autopsies", sa.Column("model_used", sa.String(100)))
    op.add_column("autopsies", sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("autopsies", sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("autopsies", sa.Column("provider_error", sa.String(100)))
    op.add_column("autopsies", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("autopsies", sa.Column("completed_at", sa.DateTime(timezone=True)))
    op.execute("""
        UPDATE autopsies a SET
          project_id=(SELECT m.project_id FROM mappings m WHERE m.id=a.mapping_id),
          owner_id=(SELECT p.owner_id FROM mappings m JOIN projects p ON p.id=m.project_id WHERE m.id=a.mapping_id),
          conversion_id=(SELECT sr.conversion_id FROM shadow_runs sr WHERE sr.id=a.shadow_run_id)
    """)
    op.execute("UPDATE autopsies SET diagnosis_category='UNKNOWN', diagnosis_json=jsonb_build_object('legacy_record', true), confidence=COALESCE(confidence, 0), evidence=COALESCE(evidence, '[]'::jsonb), suggested_corrections=CASE WHEN suggested_fix IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(suggested_fix) END WHERE status IN ('open','fix_applied','resolved','dismissed')")
    op.alter_column("autopsies", "evidence", nullable=False, server_default=sa.text("'[]'::jsonb"))
    op.create_check_constraint(
        "ck_autopsies_status", "autopsies",
        "status IN ('queued','running','completed','failed','open','fix_applied','resolved','dismissed')",
    )
    op.create_check_constraint("ck_autopsies_confidence", "autopsies", "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)")
    op.create_check_constraint(
        "ck_autopsies_phase6_links", "autopsies",
        "status IN ('open','fix_applied','resolved','dismissed') OR (shadow_run_id IS NOT NULL AND project_id IS NOT NULL AND mapping_id IS NOT NULL AND conversion_id IS NOT NULL AND owner_id IS NOT NULL)",
    )
    op.create_foreign_key("fk_autopsies_project", "autopsies", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_autopsies_conversion", "autopsies", "conversions", ["conversion_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_autopsies_owner", "autopsies", "users", ["owner_id"], ["id"], ondelete="CASCADE")
    op.create_index("idx_autopsies_shadow_created", "autopsies", ["shadow_run_id", "created_at"])
    op.create_index(
        "uq_autopsies_active_shadow", "autopsies", ["shadow_run_id"], unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_autopsies_active_shadow", table_name="autopsies")
    op.drop_index("idx_autopsies_shadow_created", table_name="autopsies")
    for name in ("fk_autopsies_owner", "fk_autopsies_conversion", "fk_autopsies_project"):
        op.drop_constraint(name, "autopsies", type_="foreignkey")
    for name in ("ck_autopsies_phase6_links", "ck_autopsies_confidence", "ck_autopsies_status"):
        op.drop_constraint(name, "autopsies", type_="check")
    op.execute("""
        UPDATE autopsies SET
          trigger_type=COALESCE(trigger_type, 'mismatch'),
          root_cause=COALESCE(root_cause, diagnosis_json->>'suspected_root_cause', 'Phase 6 diagnosis unavailable'),
          suggested_fix=COALESCE(suggested_fix, suggested_sql),
          status=CASE
            WHEN status='completed' THEN 'open'
            WHEN status='failed' THEN 'dismissed'
            WHEN status IN ('queued','running') THEN 'open'
            ELSE status
          END
    """)
    for name in (
        "completed_at", "started_at", "provider_error", "output_tokens", "input_tokens",
        "model_used", "suggested_sql", "suggested_corrections", "diagnosis_json",
        "diagnosis_category", "owner_id", "conversion_id", "project_id",
    ):
        op.drop_column("autopsies", name)
    op.alter_column("autopsies", "status", server_default="open")
    op.alter_column("autopsies", "trigger_type", nullable=False)
    op.alter_column("autopsies", "root_cause", nullable=False)
    op.alter_column("autopsies", "evidence", nullable=True, server_default=None)
    op.create_check_constraint("autopsies_status_check", "autopsies", "status IN ('open','fix_applied','resolved','dismissed')")
