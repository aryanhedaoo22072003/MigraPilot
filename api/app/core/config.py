from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://migrapilot:local@localhost:5432/migrapilot"
    jwt_secret: str = "local-tests-only-not-safe-for-production"
    cors_origins: str = "http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    ai_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    ai_max_output_tokens: int = 4096
    ai_conversion_rate_limit_per_minute: int = 5
    ai_autopsy_rate_limit_per_minute: int = 3
    ai_provider_timeout_seconds: float = 60.0
    ai_provider_max_retries: int = 1
    ai_autopsy_request_budget_seconds: float = 45.0
    ai_autopsy_task_soft_limit_seconds: int = 60
    ai_autopsy_task_hard_limit_seconds: int = 70
    ai_autopsy_stale_after_seconds: int = 300
    mask_pii: bool = True
    max_upload_bytes: int = 10 * 1024 * 1024
    max_zip_files: int = 50
    max_zip_uncompressed_bytes: int = 50 * 1024 * 1024
    parse_tasks_eager: bool = False
    shadow_loader_url: str = ""
    shadow_executor_url: str = ""
    shadow_statement_timeout_ms: int = 5000
    shadow_job_timeout_seconds: int = 30
    shadow_max_rows: int = 1000
    shadow_mismatch_sample_limit: int = 25
    shadow_decimal_tolerance: str = "0.0001"
    autopsy_max_sql_chars: int = 50_000
    autopsy_max_expression_chars: int = 2_000
    autopsy_max_transformations: int = 100
    autopsy_max_ports: int = 500
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_autopsy_timeout_envelope(self):
        if self.ai_autopsy_request_budget_seconds <= 0:
            raise ValueError("AI Autopsy request budget must be positive")
        if self.ai_autopsy_request_budget_seconds > self.ai_autopsy_task_soft_limit_seconds - 10:
            raise ValueError("AI Autopsy request budget must leave at least 10 seconds before the soft task limit")
        if self.ai_autopsy_task_hard_limit_seconds < self.ai_autopsy_task_soft_limit_seconds + 5:
            raise ValueError("AI Autopsy hard task limit must be at least 5 seconds above the soft limit")
        if self.ai_autopsy_stale_after_seconds <= self.ai_autopsy_task_hard_limit_seconds:
            raise ValueError("AI Autopsy stale threshold must exceed the hard task limit")
        return self


settings = Settings()
