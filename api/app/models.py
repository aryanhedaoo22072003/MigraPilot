from datetime import datetime
from sqlalchemy import JSON, BigInteger, Integer, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="engineer", server_default="engineer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    projects: Mapped[list["Project"]] = relationship(back_populates="owner")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_system: Mapped[str] = mapped_column(String(50), nullable=False, default="powercenter", server_default="powercenter")
    target_system: Mapped[str] = mapped_column(String(50), nullable=False, default="dbt_postgres", server_default="dbt_postgres")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    owner: Mapped[User] = relationship(back_populates="projects")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="project", passive_deletes=True)
    uploads: Mapped[list["Upload"]] = relationship(back_populates="project", passive_deletes=True)
    jobs: Mapped[list["Job"]] = relationship(back_populates="project", passive_deletes=True)


class Upload(Base):
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_xml: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded", server_default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project] = relationship(back_populates="uploads")
    mappings: Mapped[list["Mapping"]] = relationship(back_populates="upload")
    jobs: Mapped[list["Job"]] = relationship(back_populates="upload")


class Mapping(Base):
    __tablename__ = "mappings"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    upload_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("uploads.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description_ai: Mapped[str | None] = mapped_column(Text)
    complexity: Mapped[int | None] = mapped_column(SmallInteger)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project] = relationship(back_populates="mappings")
    upload: Mapped[Upload | None] = relationship(back_populates="mappings")
    transformations: Mapped[list["Transformation"]] = relationship(back_populates="mapping", cascade="all, delete-orphan", passive_deletes=True)
    lineage_edges: Mapped[list["LineageEdge"]] = relationship(back_populates="mapping", cascade="all, delete-orphan", passive_deletes=True)
    conversions: Mapped[list["Conversion"]] = relationship(back_populates="mapping", passive_deletes=True)


class Transformation(Base):
    __tablename__ = "transformations"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    logic_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    seq_order: Mapped[int] = mapped_column(Integer, nullable=False)
    mapping: Mapped[Mapping] = relationship(back_populates="transformations")
    ports: Mapped[list["Port"]] = relationship(back_populates="transformation", cascade="all, delete-orphan", passive_deletes=True)


class Port(Base):
    __tablename__ = "ports"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    transformation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("transformations.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    datatype: Mapped[str | None] = mapped_column(String(50))
    direction: Mapped[str | None] = mapped_column(String(10))
    expression: Mapped[str | None] = mapped_column(Text)
    transformation: Mapped[Transformation] = relationship(back_populates="ports")


class LineageEdge(Base):
    __tablename__ = "lineage_edges"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    from_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False)
    to_port_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ports.id", ondelete="CASCADE"), nullable=False)
    mapping: Mapped[Mapping] = relationship(back_populates="lineage_edges")


class Conversion(Base):
    __tablename__ = "conversions"
    __table_args__ = (UniqueConstraint("mapping_id", "version"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    generated_sql: Mapped[str] = mapped_column(Text, nullable=False)
    schema_yml: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    confidence_reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    risk_flags: Mapped[list | dict | None] = mapped_column(JSON)
    model_used: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    mapping: Mapped[Mapping] = relationship(back_populates="conversions")
    shadow_runs: Mapped[list["ShadowRun"]] = relationship(back_populates="conversion", passive_deletes=True)


class ShadowRun(Base):
    __tablename__ = "shadow_runs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    conversion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversions.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    fixture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    comparison_result: Mapped[str | None] = mapped_column(String(10))
    reference_row_count: Mapped[int | None] = mapped_column(Integer)
    migrated_row_count: Mapped[int | None] = mapped_column(Integer)
    matched_rows: Mapped[int | None] = mapped_column(Integer)
    missing_rows: Mapped[int | None] = mapped_column(Integer)
    unexpected_rows: Mapped[int | None] = mapped_column(Integer)
    duplicate_key_mismatches: Mapped[int | None] = mapped_column(Integer)
    column_mismatches: Mapped[int | None] = mapped_column(Integer)
    null_mismatches: Mapped[int | None] = mapped_column(Integer)
    numeric_precision_differences: Mapped[int | None] = mapped_column(Integer)
    mismatch_samples: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    execution_time_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    conversion: Mapped[Conversion] = relationship(back_populates="shadow_runs")
    autopsies: Mapped[list["Autopsy"]] = relationship(back_populates="shadow_run", passive_deletes=True)


class Autopsy(Base):
    __tablename__ = "autopsies"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    shadow_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shadow_runs.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    conversion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversions.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    diagnosis_category: Mapped[str | None] = mapped_column(String(50))
    diagnosis_json: Mapped[dict | None] = mapped_column(JSON)
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    suggested_corrections: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    suggested_sql: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    provider_error: Mapped[str | None] = mapped_column(String(100))
    celery_task_id: Mapped[str | None] = mapped_column(String(50))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shadow_run: Mapped[ShadowRun] = relationship(back_populates="autopsies")


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidates"
    __table_args__ = (UniqueConstraint("project_id", "source_autopsy_id", name="uq_knowledge_project_autopsy"),)
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    mapping_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("mappings.id", ondelete="CASCADE"), nullable=False)
    owner_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_autopsy_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("autopsies.id", ondelete="RESTRICT"), nullable=False)
    original_shadow_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("shadow_runs.id", ondelete="RESTRICT"), nullable=False)
    original_conversion_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("conversions.id", ondelete="RESTRICT"), nullable=False)
    corrected_conversion_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("conversions.id", ondelete="RESTRICT"))
    corrected_conversion_version: Mapped[int | None] = mapped_column(Integer)
    passing_shadow_run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("shadow_runs.id", ondelete="RESTRICT"))
    diagnosis_category: Mapped[str] = mapped_column(String(50), nullable=False)
    transformation_identifiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    affected_columns: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    signature_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    root_cause_summary: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_corrective_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    verified_remediation_summary: Mapped[str | None] = mapped_column(Text)
    fixture_id: Mapped[str] = mapped_column(String(100), nullable=False)
    verification_outcome: Mapped[str | None] = mapped_column(String(30))
    verification_scope: Mapped[str | None] = mapped_column(String(300))
    verification_evidence: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    events: Mapped[list["KnowledgeEvent"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True,
        order_by="KnowledgeEvent.created_at, KnowledgeEvent.id",
    )


class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    candidate_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("knowledge_candidates.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_snapshot: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    candidate: Mapped[KnowledgeCandidate] = relationship(back_populates="events")


class AIUsage(Base):
    __tablename__ = "ai_usage"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    project_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("projects.id", ondelete="CASCADE"))
    upload_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("uploads.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", server_default="queued")
    progress: Mapped[int | None] = mapped_column(SmallInteger, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    project: Mapped[Project | None] = relationship(back_populates="jobs")
    upload: Mapped[Upload | None] = relationship(back_populates="jobs")
