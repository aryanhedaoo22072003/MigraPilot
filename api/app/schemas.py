from datetime import datetime
import re
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def canonical_email(cls, email: str) -> str:
        return email.strip().lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    source_system: str = Field(default="powercenter", pattern=r"^(powercenter|odi)$")
    target_system: str = Field(default="dbt_postgres", pattern=r"^(dbt_postgres|dbt_snowflake|dbt_bigquery)$")

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        name = name.strip()
        if len(name) < 2:
            raise ValueError("Project name must be at least 2 characters")
        return name


class ProjectUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)

    @field_validator("name")
    @classmethod
    def clean_name(cls, name: str) -> str:
        name = name.strip()
        if len(name) < 2:
            raise ValueError("Project name must be at least 2 characters")
        return name


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    owner_id: int
    name: str
    source_system: str
    target_system: str
    created_at: datetime


class DashboardResponse(BaseModel):
    project: ProjectResponse
    total_mappings: int
    parsed: int
    converted: int
    verified: int
    failing: int
    converted_percent: float
    verified_percent: float
    failing_percent: float


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "migrapilot-api"


class UploadItemResponse(BaseModel):
    id: int
    file_name: str
    status: str
    job_id: int


class UploadBatchResponse(BaseModel):
    uploads: list[UploadItemResponse]


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int | None
    upload_id: int | None
    type: str
    status: str
    progress: int | None
    error: str | None
    created_at: datetime


class PortResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    datatype: str | None
    direction: str | None
    expression: str | None


class TransformationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    type: str
    logic_json: dict
    seq_order: int
    ports: list[PortResponse]


class LineageEdgeResponse(BaseModel):
    id: int
    from_port_id: int
    to_port_id: int
    from_transformation: str
    from_port: str
    to_transformation: str
    to_port: str


class MappingSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: int
    project_id: int
    upload_id: int | None
    name: str
    description: str | None = Field(validation_alias=AliasChoices("description", "description_ai"))
    status: str
    created_at: datetime


class MappingDetailResponse(MappingSummaryResponse):
    transformations: list[TransformationResponse]
    lineage_edges: list[LineageEdgeResponse]


class ConversionRiskFlag(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Z0-9_]+$")
    severity: str = Field(pattern=r"^(low|medium|high)$")
    message: str = Field(min_length=3, max_length=1000)
    transformation: str | None = Field(default=None, max_length=255)
    port: str | None = Field(default=None, max_length=255)


class ConversionAIOutput(BaseModel):
    generated_sql: str = Field(min_length=20, max_length=200_000)
    schema_yml: str = Field(min_length=10, max_length=100_000)
    confidence: int = Field(ge=0, le=100)
    confidence_reasons: list[str] = Field(min_length=1, max_length=20)
    risk_flags: list[ConversionRiskFlag] = Field(default_factory=list, max_length=100)

    @field_validator("generated_sql")
    @classmethod
    def read_only_model_sql(cls, sql: str) -> str:
        stripped = sql.strip()
        normalized = re.sub(r"\{\{.*?\}\}", "", stripped, flags=re.DOTALL).lstrip()
        if not re.match(r"^(WITH|SELECT)\b", normalized, flags=re.IGNORECASE):
            raise ValueError("Generated dbt SQL must be a SELECT or WITH query")
        if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE)\b", normalized, flags=re.IGNORECASE):
            raise ValueError("Generated SQL contains a prohibited write or DDL statement")
        return stripped

    @field_validator("schema_yml")
    @classmethod
    def dbt_schema_document(cls, value: str) -> str:
        if "version:" not in value or "models:" not in value:
            raise ValueError("schema_yml must contain dbt version and models keys")
        return value.strip()

    @field_validator("confidence_reasons")
    @classmethod
    def clean_reasons(cls, reasons: list[str]) -> list[str]:
        cleaned = [reason.strip() for reason in reasons if reason.strip()]
        if not cleaned:
            raise ValueError("At least one confidence reason is required")
        return cleaned


class RegenerateConversionRequest(BaseModel):
    user_comment: str = Field(min_length=2, max_length=2000)

    @field_validator("user_comment")
    @classmethod
    def clean_comment(cls, value: str) -> str:
        return value.strip()


class ConversionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_id: int
    version: int
    generated_sql: str
    schema_yml: str | None
    confidence: int | None
    confidence_reasons: list[str]
    risk_flags: list[ConversionRiskFlag]
    model_used: str | None
    created_at: datetime


class ConversionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    mapping_id: int
    version: int
    confidence: int | None
    model_used: str | None
    created_at: datetime


class ShadowRunCreate(BaseModel):
    fixture_id: str = Field(min_length=1, max_length=100)


class ShadowRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    mapping_id: int
    conversion_id: int
    fixture_id: str
    status: str
    comparison_result: str | None
    reference_row_count: int | None
    migrated_row_count: int | None
    matched_rows: int | None
    missing_rows: int | None
    unexpected_rows: int | None
    duplicate_key_mismatches: int | None
    column_mismatches: int | None
    null_mismatches: int | None
    numeric_precision_differences: int | None
    mismatch_samples: list
    execution_time_ms: int | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


AutopsyCategory = Literal[
    "EXPRESSION_MISMATCH", "FILTER_MISMATCH", "NULL_SEMANTICS",
    "DATA_TYPE_CONVERSION", "DECIMAL_PRECISION", "JOIN_BEHAVIOR",
    "LOOKUP_BEHAVIOR", "DUPLICATE_KEYS", "MISSING_ROWS",
    "UNEXPECTED_ROWS", "SQL_EXECUTION", "UNSUPPORTED_TRANSFORMATION",
    "UNKNOWN", "NEEDS_MORE_EVIDENCE",
]


class AutopsyEvidenceReference(BaseModel):
    reference: str = Field(min_length=3, max_length=300)
    observation: str = Field(min_length=3, max_length=1000)


class AutopsyAIOutput(BaseModel):
    summary: str = Field(min_length=10, max_length=2000)
    diagnosis_category: AutopsyCategory
    suspected_root_cause: str = Field(min_length=10, max_length=4000)
    observed_facts: list[str] = Field(min_length=1, max_length=30)
    hypotheses: list[str] = Field(min_length=1, max_length=20)
    affected_transformations: list[str] = Field(default_factory=list, max_length=100)
    affected_columns: list[str] = Field(default_factory=list, max_length=200)
    supporting_evidence: list[AutopsyEvidenceReference] = Field(min_length=1, max_length=50)
    confidence: int = Field(ge=0, le=100)
    confidence_reasons: list[str] = Field(min_length=1, max_length=20)
    suggested_corrective_actions: list[str] = Field(min_length=1, max_length=20)
    suggested_sql: str | None = Field(default=None, max_length=50_000)
    risks_and_limitations: list[str] = Field(min_length=1, max_length=20)
    recommended_verification_steps: list[str] = Field(min_length=1, max_length=20)
    more_evidence_required: bool

    @field_validator(
        "observed_facts", "hypotheses", "affected_transformations", "affected_columns",
        "confidence_reasons", "suggested_corrective_actions", "risks_and_limitations",
        "recommended_verification_steps",
    )
    @classmethod
    def bounded_clean_strings(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value.strip()]
        if any(len(value) > 1000 for value in cleaned):
            raise ValueError("Autopsy list entries must not exceed 1000 characters")
        return cleaned

    @field_validator("suggested_sql")
    @classmethod
    def safe_unverified_sql(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        normalized = re.sub(r"\{\{.*?\}\}", "", stripped, flags=re.DOTALL).lstrip()
        if not re.match(r"^(WITH|SELECT)\b", normalized, flags=re.IGNORECASE):
            raise ValueError("Suggested SQL must be a complete read-only SELECT or WITH query")
        if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|CREATE|CALL|COPY)\b", normalized, flags=re.IGNORECASE):
            raise ValueError("Suggested SQL contains a prohibited write, DDL, or execution statement")
        if ";" in stripped.rstrip(";"):
            raise ValueError("Suggested SQL must contain exactly one statement")
        return stripped

    @model_validator(mode="after")
    def required_diagnostic_lists_are_not_blank(self):
        required = (
            self.observed_facts, self.hypotheses, self.confidence_reasons,
            self.suggested_corrective_actions, self.risks_and_limitations,
            self.recommended_verification_steps,
        )
        if any(not values for values in required):
            raise ValueError("Required Autopsy diagnostic lists must contain non-blank entries")
        return self


class AutopsyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    shadow_run_id: int
    project_id: int
    mapping_id: int
    conversion_id: int
    status: str
    diagnosis_category: str | None
    diagnosis_json: AutopsyAIOutput | None
    confidence: int | None
    evidence: list
    suggested_corrections: list
    suggested_sql: str | None
    suggested_sql_verified: bool = False
    model_used: str | None
    input_tokens: int
    output_tokens: int
    provider_error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


KnowledgeStatus = Literal["draft", "verified", "published", "rejected", "archived"]


class KnowledgeVerificationRequest(BaseModel):
    passing_shadow_run_id: int = Field(gt=0)


class KnowledgeReviewRequest(BaseModel):
    decision: Literal["approve", "reject", "archive"]
    notes: str = Field(min_length=3, max_length=4000)

    @field_validator("notes")
    @classmethod
    def clean_notes(cls, value: str) -> str:
        return value.strip()


class KnowledgeEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    actor_id: int
    event_type: str
    from_status: str | None
    to_status: str
    notes: str | None
    evidence_snapshot: dict | None
    created_at: datetime


class KnowledgeCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    mapping_id: int
    owner_id: int
    source_autopsy_id: int
    original_shadow_run_id: int
    original_conversion_id: int
    corrected_conversion_id: int | None
    corrected_conversion_version: int | None
    passing_shadow_run_id: int | None
    diagnosis_category: str
    transformation_identifiers: list[str]
    affected_columns: list[str]
    signature_metadata: dict
    root_cause_summary: str
    suggested_corrective_actions: list[str]
    verified_remediation_summary: str | None
    fixture_id: str
    verification_outcome: str | None
    verification_scope: str | None
    verification_evidence: dict | None
    status: KnowledgeStatus
    reviewer_id: int | None
    review_notes: str | None
    created_at: datetime
    verified_at: datetime | None
    approved_at: datetime | None
    published_at: datetime | None
    archived_at: datetime | None
    events: list[KnowledgeEventResponse] = Field(default_factory=list)


class KnowledgeCandidateListResponse(BaseModel):
    items: list[KnowledgeCandidateResponse]
    total: int
    limit: int
    offset: int


class KnowledgeSuggestionResponse(BaseModel):
    knowledge_id: int
    diagnosis_category: str
    relevance: Literal["HIGH", "MEDIUM", "LOW"]
    reasons: list[str]
    root_cause_summary: str
    suggested_corrective_actions: list[str]
    verified_remediation_summary: str
    fixture_id: str
    corrected_conversion_version: int
    published_at: datetime
    advisory: str = "Relevant verified knowledge is advisory and does not prove this fix applies."
