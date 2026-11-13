from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import auth, autopsies, conversions, knowledge, phase2, projects, shadow_runs
from app.schemas import HealthResponse

app = FastAPI(title="MigraPilot API", version="0.7.0", description="AI-powered ETL migration copilot — verified failure knowledge backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",") if x.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(phase2.router, prefix="/api/v1")
app.include_router(conversions.router, prefix="/api/v1")
app.include_router(shadow_runs.router, prefix="/api/v1")
app.include_router(autopsies.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")


@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
async def health():
    return HealthResponse()
