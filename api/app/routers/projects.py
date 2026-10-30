from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.deps import current_user, owned_project, require_write
from app.models import Mapping, Project, User
from app.schemas import DashboardResponse, ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return (await db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.created_at.desc(), Project.id.desc()))).all()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    require_write(user)
    project = Project(owner_id=user.id, **body.model_dump())
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    return await owned_project(db, project_id, user)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: int, body: ProjectUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    require_write(user)
    project = await owned_project(db, project_id, user)
    project.name = body.name.strip()
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    require_write(user)
    project = await owned_project(db, project_id, user)
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/dashboard", response_model=DashboardResponse)
async def project_dashboard(project_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    project = await owned_project(db, project_id, user)
    rows = (await db.execute(select(Mapping.status, func.count(Mapping.id)).where(Mapping.project_id == project_id).group_by(Mapping.status))).all()
    counts = {name: count for name, count in rows}
    total = sum(counts.values())
    parsed = counts.get("parsed", 0)
    converted = counts.get("converted", 0)
    verified = counts.get("verified", 0)
    failing = counts.get("failing", 0)
    pct = lambda x: round(100 * x / total, 1) if total else 0.0
    return DashboardResponse(
        project=ProjectResponse.model_validate(project), total_mappings=total,
        parsed=parsed, converted=converted, verified=verified, failing=failing,
        converted_percent=pct(converted + verified), verified_percent=pct(verified), failing_percent=pct(failing),
    )
