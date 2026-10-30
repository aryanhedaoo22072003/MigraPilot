from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://migrapilot:local@localhost:5432/migrapilot"
    jwt_secret: str = "local-tests-only-not-safe-for-production"
    cors_origins: str = "http://localhost:5173"
    redis_url: str = "redis://localhost:6379/0"
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    mask_pii: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
