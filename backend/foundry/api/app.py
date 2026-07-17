"""Foundry API — projects, kanban tasks, agent prompt queue."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload

from foundry.auth import (
    create_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)
from foundry.config import settings
from foundry.database import Base, SessionLocal, engine, get_db
from foundry.migrate import (
    migrate_agent_prompts_to_tasks,
    migrate_project_repo_slug,
    migrate_project_visibility,
    migrate_project_customer,
    migrate_project_priority,
    migrate_task_statuses,
    migrate_user_admin_flags,
)
from foundry.deploy.site import (
    SiteDeployError,
    project_supports_site_deploy,
    run_site_deploy,
)
from foundry.models import (
    AGENT_STATUSES,
    PROJECT_STAGES,
    PROJECT_STATUSES,
    PROJECT_VISIBILITIES,
    PROJECT_PRIORITIES,
    TASK_STATUSES,
    AgentPrompt,
    Project,
    Task,
    User,
)
from foundry.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AgentPromptCreate,
    AgentPromptOut,
    AgentPromptReorder,
    AgentPromptUpdate,
    PasswordChange,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    SiteDeployOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TokenResponse,
    UserLogin,
    UserOut,
)
from foundry.seed import seed_database

WEB_DIR = Path(__file__).resolve().parent.parent.parent.parent / "web"

app = FastAPI(title="Perrin Research Foundry", version="0.1.0")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    migrate_agent_prompts_to_tasks(engine)
    migrate_task_statuses(engine)
    migrate_project_visibility(engine)
    migrate_project_repo_slug(engine)
    migrate_project_customer(engine)
    migrate_project_priority(engine)
    migrate_user_admin_flags(engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


def project_out(project: Project, db: Session) -> ProjectOut:
    counts = Counter(t.status for t in project.tasks)
    return ProjectOut(
        id=project.id,
        ref=project.ref,
        name=project.name,
        hypothesis=project.hypothesis,
        customer=getattr(project, "customer", "") or "",
        form=project.form,
        stage=project.stage,
        status=project.status,
        priority=getattr(project, "priority", None) or "normal",
        visibility=getattr(project, "visibility", None) or "public",
        repo_slug=getattr(project, "repo_slug", None) or "",
        owner_id=project.owner_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        task_counts=dict(counts),
        can_deploy_site=project_supports_site_deploy(project.ref),
    )


def prompt_out(prompt: AgentPrompt, db: Session) -> AgentPromptOut:
    task = prompt.task or db.get(Task, prompt.task_id)
    project_ref = task.project.ref if task and task.project else None
    task_title = task.title if task else None
    return AgentPromptOut(
        id=prompt.id,
        task_id=prompt.task_id,
        title=prompt.title,
        prompt_text=prompt.prompt_text,
        status=prompt.status,
        priority=prompt.priority,
        result_notes=prompt.result_notes,
        created_by_id=prompt.created_by_id,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        task_title=task_title,
        project_ref=project_ref,
    )


# --- Auth ---

@app.post("/api/auth/register", status_code=403)
def register():
    """Public registration is closed — admins create accounts via POST /api/users."""
    raise HTTPException(403, "Public registration is closed. Ask an admin to create your account.")


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: UserLogin, db: Annotated[Session, Depends(get_db)]):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    if not getattr(user, "is_active", True):
        raise HTTPException(401, "Account access has been revoked")
    return TokenResponse(access_token=create_token(user.id))


@app.get("/api/auth/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]):
    return user


@app.post("/api/auth/change-password", response_model=UserOut)
def change_password(
    body: PasswordChange,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    db.refresh(user)
    return user


def _active_admin_count(db: Session) -> int:
    return (
        db.query(User)
        .filter(User.is_admin == True, User.is_active == True)  # noqa: E712
        .count()
    )


@app.get("/api/users", response_model=list[UserOut])
def list_users(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    return db.query(User).order_by(User.email).all()


@app.post("/api/users", response_model=UserOut, status_code=201)
def create_user(
    body: AdminUserCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(400, "Email already registered")
    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        is_admin=body.is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.patch("/api/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)

    new_is_admin = data.get("is_admin", user.is_admin)
    new_is_active = data.get("is_active", user.is_active)
    was_active_admin = user.is_admin and user.is_active
    will_be_active_admin = new_is_admin and new_is_active
    if was_active_admin and not will_be_active_admin and _active_admin_count(db) <= 1:
        raise HTTPException(400, "Cannot demote or revoke the last active admin")

    for key, val in data.items():
        setattr(user, key, val)
    if password is not None:
        user.password_hash = hash_password(password)
    db.commit()
    db.refresh(user)
    return user


# --- Projects ---

@app.get("/api/projects", response_model=list[ProjectOut])
def list_projects(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status: str | None = "active",
):
    q = db.query(Project)
    if status:
        q = q.filter(Project.status == status)
    return [project_out(p, db) for p in q.order_by(Project.ref).all()]


@app.post("/api/projects", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if db.query(Project).filter(Project.ref == body.ref).first():
        raise HTTPException(400, "Project ref already exists")
    if body.stage not in PROJECT_STAGES:
        raise HTTPException(400, f"Invalid stage; use one of {PROJECT_STAGES}")
    if body.priority not in PROJECT_PRIORITIES:
        raise HTTPException(400, f"Invalid priority; use one of {PROJECT_PRIORITIES}")
    if body.visibility not in PROJECT_VISIBILITIES:
        raise HTTPException(400, f"Invalid visibility; use one of {PROJECT_VISIBILITIES}")
    project = Project(**body.model_dump(), owner_id=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


@app.get("/api/projects/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project_out(project, db)


@app.patch("/api/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    body: ProjectUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    data = body.model_dump(exclude_unset=True)
    if "stage" in data and data["stage"] not in PROJECT_STAGES:
        raise HTTPException(400, f"Invalid stage; use one of {PROJECT_STAGES}")
    if "status" in data and data["status"] not in PROJECT_STATUSES:
        raise HTTPException(400, f"Invalid status; use one of {PROJECT_STATUSES}")
    if "priority" in data and data["priority"] not in PROJECT_PRIORITIES:
        raise HTTPException(400, f"Invalid priority; use one of {PROJECT_PRIORITIES}")
    if "visibility" in data and data["visibility"] not in PROJECT_VISIBILITIES:
        raise HTTPException(400, f"Invalid visibility; use one of {PROJECT_VISIBILITIES}")
    for key, val in data.items():
        setattr(project, key, val)
    db.commit()
    db.refresh(project)
    return project_out(project, db)


def _site_deploy_or_http_error(db: Session) -> SiteDeployOut:
    try:
        return run_site_deploy(db)
    except SiteDeployError as exc:
        if exc.detail is not None:
            raise HTTPException(exc.status_code, detail=exc.detail) from exc
        raise HTTPException(exc.status_code, exc.message) from exc


@app.post("/api/site/deploy", response_model=SiteDeployOut)
def deploy_public_site_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Sync active portfolio projects and publish the public site."""
    return _site_deploy_or_http_error(db)


@app.post("/api/projects/{project_id}/deploy-site", response_model=SiteDeployOut)
def deploy_site(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Legacy endpoint — use POST /api/site/deploy. Kept for PR-000 compatibility."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if not project_supports_site_deploy(project.ref):
        raise HTTPException(
            400,
            f"Site deploy is only available for project {project.ref}.",
        )
    return _site_deploy_or_http_error(db)


# --- Tasks (kanban) ---

@app.get("/api/projects/{project_id}/tasks", response_model=list[TaskOut])
def list_tasks(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    return (
        db.query(Task)
        .filter(Task.project_id == project_id)
        .order_by(Task.status, Task.position)
        .all()
    )


@app.post("/api/projects/{project_id}/tasks", response_model=TaskOut, status_code=201)
def create_task(
    project_id: int,
    body: TaskCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    if body.status not in TASK_STATUSES:
        raise HTTPException(400, f"Invalid status; use one of {TASK_STATUSES}")
    max_pos = (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.status == body.status)
        .count()
    )
    task = Task(
        project_id=project_id,
        title=body.title,
        description=body.description,
        status=body.status,
        position=max_pos,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@app.patch("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    body: TaskUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in TASK_STATUSES:
        raise HTTPException(400, f"Invalid status; use one of {TASK_STATUSES}")
    for key, val in data.items():
        setattr(task, key, val)
    db.commit()
    db.refresh(task)
    return task


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    db.delete(task)
    db.commit()


# --- Agent prompts ---

@app.get("/api/agent-prompts", response_model=list[AgentPromptOut])
def list_prompts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    status: str | None = None,
    task_id: int | None = None,
    project_id: int | None = None,
):
    q = db.query(AgentPrompt).options(joinedload(AgentPrompt.task).joinedload(Task.project))
    if status:
        q = q.filter(AgentPrompt.status == status)
    if task_id is not None:
        q = q.filter(AgentPrompt.task_id == task_id)
    if project_id is not None:
        q = q.filter(AgentPrompt.task.has(Task.project_id == project_id))
    prompts = q.order_by(AgentPrompt.priority.desc(), AgentPrompt.created_at).all()
    return [prompt_out(p, db) for p in prompts]


@app.get("/api/tasks/{task_id}/agent-prompts", response_model=list[AgentPromptOut])
def list_task_prompts(
    task_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Task, task_id):
        raise HTTPException(404, "Task not found")
    prompts = (
        db.query(AgentPrompt)
        .options(joinedload(AgentPrompt.task).joinedload(Task.project))
        .filter(AgentPrompt.task_id == task_id)
        .order_by(AgentPrompt.priority.desc(), AgentPrompt.created_at)
        .all()
    )
    return [prompt_out(p, db) for p in prompts]


@app.get("/api/agent-prompts/pending", response_model=list[AgentPromptOut])
def pending_prompts(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Queue for agents to pick up."""
    prompts = (
        db.query(AgentPrompt)
        .options(joinedload(AgentPrompt.task).joinedload(Task.project))
        .filter(AgentPrompt.status == "pending")
        .order_by(AgentPrompt.priority.desc(), AgentPrompt.created_at)
        .all()
    )
    return [prompt_out(p, db) for p in prompts]


@app.post("/api/agent-prompts", response_model=AgentPromptOut, status_code=201)
def create_prompt(
    body: AgentPromptCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Task, body.task_id):
        raise HTTPException(404, "Task not found")
    prompt = AgentPrompt(**body.model_dump(), created_by_id=user.id)
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return prompt_out(prompt, db)


@app.post("/api/agent-prompts/reorder", response_model=list[AgentPromptOut])
def reorder_prompts(
    body: AgentPromptReorder,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Set queue order top-to-bottom; highest priority first."""
    count = len(body.ordered_ids)
    for i, prompt_id in enumerate(body.ordered_ids):
        prompt = db.get(AgentPrompt, prompt_id)
        if not prompt:
            raise HTTPException(404, f"Prompt {prompt_id} not found")
        prompt.priority = count - i
    db.commit()
    prompts = (
        db.query(AgentPrompt)
        .options(joinedload(AgentPrompt.task).joinedload(Task.project))
        .order_by(AgentPrompt.priority.desc(), AgentPrompt.created_at)
        .all()
    )
    return [prompt_out(p, db) for p in prompts]


@app.patch("/api/agent-prompts/{prompt_id}", response_model=AgentPromptOut)
def update_prompt(
    prompt_id: int,
    body: AgentPromptUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    prompt = db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in AGENT_STATUSES:
        raise HTTPException(400, f"Invalid status; use one of {AGENT_STATUSES}")
    for key, val in data.items():
        setattr(prompt, key, val)
    db.commit()
    db.refresh(prompt)
    return prompt_out(prompt, db)


@app.delete("/api/agent-prompts/{prompt_id}", status_code=204)
def delete_prompt(
    prompt_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    prompt = db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Prompt not found")
    db.delete(prompt)
    db.commit()


# --- Static web UI ---

if WEB_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/{path:path}")
    def spa_fallback(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(WEB_DIR / "index.html")
