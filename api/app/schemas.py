from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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
