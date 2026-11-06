from datetime import datetime
import re
from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator


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
