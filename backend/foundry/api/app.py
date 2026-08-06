"""Foundry API — projects, kanban tasks, agent prompt queue."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import secrets
import hashlib
import hmac
from pathlib import Path
import sys
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import or_
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
from foundry.eval_client import EvalClient, EvalClientError
from foundry.forms import (
    capture_agent_prompt_text,
    normalize_form,
    required_release_checks,
)
from foundry.github_client import GitHubClient, GitHubClientError
from foundry.migrate import (
    migrate_agent_prompts_to_tasks,
    migrate_agent_execution_fields,
    migrate_external_idempotency_keys,
    migrate_project_repo_slug,
    migrate_project_visibility,
    migrate_project_customer,
    migrate_project_priority,
    migrate_task_statuses,
    migrate_user_admin_flags,
    migrate_workflow_fields,
)
from foundry.deploy.site import (
    SiteDeployError,
    project_supports_site_deploy,
    run_site_deploy,
)
from foundry.models import (
    AGENT_STATUSES,
    EXPERIMENT_STATUSES,
    GATE_OUTCOMES,
    PROJECT_STAGES,
    PROJECT_STATUSES,
    PROJECT_VISIBILITIES,
    PROJECT_PRIORITIES,
    TASK_STATUSES,
    AgentPrompt,
    Artifact,
    Experiment,
    EvaluationCampaignLink,
    GateReview,
    IntegrationEvent,
    MetricObservation,
    Project,
    ProjectDossier,
    Release,
    DeploymentAdapter,
    DeploymentRun,
    StageTransition,
    Task,
    User,
)
from foundry.schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AgentPromptCreate,
    AgentClaimRequest,
    AgentCompleteRequest,
    AgentHeartbeatRequest,
    AgentPromptClaimOut,
    AgentPromptOut,
    AgentPromptReorder,
    AgentPromptUpdate,
    ArtifactCreate,
    ArtifactOut,
    ExperimentCreate,
    ExperimentOut,
    ExperimentUpdate,
    EvaluationCampaignLinkOut,
    EvaluationCampaignRequest,
    GateReviewCreate,
    GateReviewOut,
    MetricObservationCreate,
    MetricObservationOut,
    ReleaseCreate,
    ReleaseOut,
    DeploymentAdapterCreate,
    DeploymentAdapterOut,
    DeploymentRunOut,
    PasswordChange,
    ProjectCreate,
    ProjectOut,
    ProjectDossierOut,
    ProjectDossierUpsert,
    ProjectUpdate,
    ProjectWorkflowOut,
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

eval_app = None
eval_on_startup = None
if settings.eval_backend_path:
    eval_backend = str(Path(settings.eval_backend_path).expanduser().resolve())
    if eval_backend not in sys.path:
        sys.path.insert(0, eval_backend)
    from foundry_eval.api.app import app as eval_app
    from foundry_eval.api.app import on_startup as eval_on_startup

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
    migrate_external_idempotency_keys(engine)
    migrate_agent_execution_fields(engine)
    migrate_workflow_fields(engine)
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    if eval_on_startup:
        eval_on_startup()


def project_out(project: Project, db: Session) -> ProjectOut:
    counts = Counter(t.status for t in project.tasks)
    blockers = _gate_blockers(db, project)
    expected = {"idea": 7, "prototype": 2, "evaluation": 2, "shipped": 0}.get(
        project.stage, 0
    )
    coverage = 1.0 if expected == 0 else max(0.0, 1.0 - len(blockers) / expected)
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
        gate_blockers=blockers,
        evidence_coverage=coverage,
    )


def prompt_out(prompt: AgentPrompt, db: Session) -> AgentPromptOut:
    task = prompt.task or db.get(Task, prompt.task_id)
    project = task.project if task else None
    project_ref = project.ref if project else None
    task_title = task.title if task else None
    repo_slug = (getattr(project, "repo_slug", None) or "").strip() if project else ""
    repo_cwd = ""
    if repo_slug and settings.repos_root.strip():
        # Emit a path hint even when the API host has no checkout (e.g. VPS).
        # Workers validate the directory exists on their machine.
        candidate = Path(settings.repos_root).expanduser() / repo_slug
        repo_cwd = str(candidate.resolve() if candidate.is_dir() else candidate)
    return AgentPromptOut(
        id=prompt.id,
        task_id=prompt.task_id,
        title=prompt.title,
        external_key=prompt.external_key,
        prompt_text=prompt.prompt_text,
        status=prompt.status,
        priority=prompt.priority,
        result_notes=prompt.result_notes,
        result_json=json.loads(prompt.result_json or "{}"),
        error=prompt.error,
        worker_id=prompt.worker_id,
        lease_expires_at=prompt.lease_expires_at,
        heartbeat_at=prompt.heartbeat_at,
        attempts=prompt.attempts,
        runtime_seconds=prompt.runtime_seconds,
        cost_usd=prompt.cost_usd,
        artifact_refs=json.loads(prompt.artifact_refs_json or "[]"),
        created_by_id=prompt.created_by_id,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        task_title=task_title,
        project_ref=project_ref,
        repo_slug=repo_slug,
        repo_cwd=repo_cwd,
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
    # Default active-only; pass status=all (or empty) to include archived.
    if status and status != "all":
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
    if body.stage != "idea":
        raise HTTPException(400, "New projects enter at idea; use a gate review to advance")
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
    if "stage" in data:
        raise HTTPException(
            400, "Project stage is gate-controlled; use POST /api/projects/{id}/gate-reviews"
        )
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


def _gate_review_out(review: GateReview) -> GateReviewOut:
    return GateReviewOut(
        id=review.id,
        project_id=review.project_id,
        reviewer_id=review.reviewer_id,
        from_stage=review.from_stage,
        target_stage=review.target_stage,
        outcome=review.outcome,
        policy_version=review.policy_version,
        rationale=review.rationale,
        evidence_refs=json.loads(review.evidence_refs_json or "[]"),
        unresolved_risks=review.unresolved_risks,
        next_action=review.next_action,
        wip_override=review.wip_override,
        created_at=review.created_at,
    )


def _record_metric_once(
    db: Session,
    project: Project,
    key: str,
    value: float,
    unit: str,
    source: str,
) -> None:
    exists = (
        db.query(MetricObservation)
        .filter(
            MetricObservation.project_id == project.id,
            MetricObservation.key == key,
        )
        .first()
    )
    if exists is None:
        db.add(
            MetricObservation(
                project_id=project.id,
                key=key,
                value=value,
                unit=unit,
                source=source,
            )
        )


def _gate_blockers(db: Session, project: Project) -> list[str]:
    blockers: list[str] = []
    if project.stage == "idea":
        dossier = project.dossier
        required = {
            "customer/requestor": project.customer,
            "hypothesis": project.hypothesis,
            "observable problem": dossier.observable_problem if dossier else "",
            "expected value": dossier.expected_value if dossier else "",
            "falsification condition": dossier.falsification_condition if dossier else "",
            "minimum testable artifact": (
                dossier.minimum_testable_artifact if dossier else ""
            ),
            "success criteria": dossier.success_criteria if dossier else "",
        }
        blockers.extend(
            f"Missing {label}" for label, value in required.items() if not str(value).strip()
        )
    elif project.stage == "prototype":
        experiment = (
            db.query(Experiment)
            .filter(
                Experiment.project_id == project.id,
                Experiment.status.in_(("running", "completed")),
            )
            .order_by(Experiment.created_at.desc())
            .first()
        )
        if experiment is None:
            blockers.append("No running or completed experiment")
        elif not experiment.acceptance_criteria.strip():
            blockers.append("Experiment has no acceptance criteria")
        if not any(artifact.immutable for artifact in project.artifacts):
            blockers.append("No immutable artifact")
    elif project.stage == "evaluation":
        campaign = (
            db.query(EvaluationCampaignLink)
            .filter(
                EvaluationCampaignLink.project_id == project.id,
                EvaluationCampaignLink.status == "completed",
            )
            .order_by(EvaluationCampaignLink.updated_at.desc())
            .first()
        )
        if campaign is None:
            blockers.append("No completed evaluation campaign")
        else:
            packet = json.loads(campaign.packet_json or "{}")
            if packet.get("confidence") != "sufficient":
                blockers.append("Evaluation sample target is not satisfied")
            evidence_refs = packet.get("evidence_refs") or []
            if not evidence_refs:
                blockers.append("No versioned evaluation evidence references")
            immutable = sorted(
                (artifact for artifact in project.artifacts if artifact.immutable),
                key=lambda artifact: artifact.created_at,
                reverse=True,
            )
            if immutable and immutable[0].uri not in evidence_refs:
                blockers.append("Evaluation artifacts are stale")
            dimensions = (
                (packet.get("quantitative_results") or {}).get("dimensions") or {}
            )
            if any(info.get("mean") is None for info in dimensions.values()):
                blockers.append("Required rubric dimensions lack scored evidence")
            if normalize_form(project.form) == "physical":
                testability = packet.get("testability") or {}
                if not testability:
                    blockers.append("Evaluation decision packet lacks testability assessment")
                elif testability.get("can_test") is False:
                    blockers.append(
                        "Artifact set cannot test the stated value claims "
                        "(iterate on mockup package)"
                    )
    return blockers


def _provision_repo_artifact(db: Session, project: Project) -> tuple[str, bool]:
    if not project.repo_slug:
        raise HTTPException(400, "Set repo_slug before provisioning")
    try:
        client = GitHubClient()
        try:
            remote = client.ensure_repository(
                project.repo_slug,
                description=f"{project.ref}: {project.hypothesis}"[:350],
                private=project.visibility != "public",
            )
        finally:
            client.close()
    except GitHubClientError as exc:
        raise HTTPException(502, str(exc)) from exc
    uri = str(remote["html_url"])
    existing = (
        db.query(Artifact)
        .filter(Artifact.project_id == project.id, Artifact.uri == uri)
        .first()
    )
    if existing is None:
        db.add(
            Artifact(
                project_id=project.id,
                kind="repository",
                title=f"{project.ref} repository",
                uri=uri,
                version=str(remote.get("default_branch") or "main"),
                immutable=False,
                checks_status="pending",
            )
        )
    return uri, existing is None


@app.put("/api/projects/{project_id}/dossier", response_model=ProjectDossierOut)
def upsert_project_dossier(
    project_id: int,
    body: ProjectDossierUpsert,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    dossier = project.dossier or ProjectDossier(project_id=project.id)
    for key, value in body.model_dump().items():
        setattr(dossier, key, value)
    db.add(dossier)
    db.commit()
    db.refresh(dossier)
    return dossier


@app.post("/api/projects/{project_id}/experiments", response_model=ExperimentOut)
def create_experiment(
    project_id: int,
    body: ExperimentCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if body.status not in EXPERIMENT_STATUSES:
        raise HTTPException(400, f"Invalid experiment status; use {EXPERIMENT_STATUSES}")
    row = Experiment(project_id=project_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.patch("/api/experiments/{experiment_id}", response_model=ExperimentOut)
def update_experiment(
    experiment_id: int,
    body: ExperimentUpdate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    row = db.get(Experiment, experiment_id)
    if not row:
        raise HTTPException(404, "Experiment not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] not in EXPERIMENT_STATUSES:
        raise HTTPException(400, f"Invalid experiment status; use {EXPERIMENT_STATUSES}")
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/projects/{project_id}/artifacts", response_model=ArtifactOut)
def create_artifact(
    project_id: int,
    body: ArtifactCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if body.experiment_id is not None:
        experiment = db.get(Experiment, body.experiment_id)
        if not experiment or experiment.project_id != project_id:
            raise HTTPException(400, "Experiment does not belong to project")
    row = Artifact(project_id=project_id, **body.model_dump())
    db.add(row)
    db.flush()
    age = datetime.now(timezone.utc) - project.created_at.replace(tzinfo=timezone.utc)
    _record_metric_once(
        db,
        project,
        "time_to_first_artifact",
        age.total_seconds(),
        "seconds",
        f"artifact:{row.id}",
    )
    db.commit()
    db.refresh(row)
    return row


@app.post(
    "/api/projects/{project_id}/metrics", response_model=MetricObservationOut
)
def create_metric_observation(
    project_id: int,
    body: MetricObservationCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    data = body.model_dump()
    if data["observed_at"] is None:
        data["observed_at"] = datetime.now(timezone.utc)
    row = MetricObservation(project_id=project_id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post(
    "/api/projects/{project_id}/gate-reviews", response_model=GateReviewOut
)
def create_gate_review(
    project_id: int,
    body: GateReviewCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if body.outcome not in GATE_OUTCOMES:
        raise HTTPException(400, f"Invalid outcome; use {GATE_OUTCOMES}")
    next_stage = {
        "idea": "prototype",
        "prototype": "evaluation",
        "evaluation": "shipped",
        "shipped": "shipped",
    }[project.stage]
    target_stage = next_stage if body.outcome == "advance" else project.stage
    if body.outcome == "advance":
        blockers = _gate_blockers(db, project)
        if blockers:
            raise HTTPException(409, {"message": "Gate is blocked", "blockers": blockers})
        limit = {"prototype": 3, "evaluation": 3, "shipped": 2}.get(target_stage)
        if limit is not None:
            active_count = (
                db.query(Project)
                .filter(
                    Project.id != project.id,
                    Project.status == "active",
                    Project.stage == target_stage,
                )
                .count()
            )
            if active_count >= limit:
                if not body.wip_override or not user.is_admin:
                    raise HTTPException(
                        409, f"WIP limit reached for {target_stage}: {limit}"
                    )
                if not body.unresolved_risks.strip() or not body.next_action.strip():
                    raise HTTPException(
                        400,
                        "WIP override requires constrained resource/risks and expiry in next_action",
                    )
    elif body.outcome in ("iterate", "hold") and not body.next_action.strip():
        raise HTTPException(400, "iterate/hold decisions require next_action")

    review = GateReview(
        project_id=project.id,
        reviewer_id=user.id,
        from_stage=project.stage,
        target_stage=target_stage,
        outcome=body.outcome,
        policy_version=body.policy_version,
        rationale=body.rationale,
        evidence_refs_json=json.dumps(body.evidence_refs),
        unresolved_risks=body.unresolved_risks,
        next_action=body.next_action,
        wip_override=body.wip_override,
    )
    db.add(review)
    db.flush()
    if project.stage == "evaluation":
        campaign_link = (
            db.query(EvaluationCampaignLink)
            .filter(
                EvaluationCampaignLink.project_id == project.id,
                EvaluationCampaignLink.status == "completed",
            )
            .order_by(EvaluationCampaignLink.updated_at.desc())
            .first()
        )
        if campaign_link and campaign_link.decision_status == "pending":
            decision = body.outcome if body.outcome != "hold" else "inconclusive"
            status = (
                "approved"
                if decision == campaign_link.recommendation
                else "overridden"
            )
            client = EvalClient()
            try:
                packet = client.record_decision(
                    project.ref,
                    campaign_link.eval_campaign_id,
                    {
                        "status": status,
                        "recommendation": decision,
                        "rationale": body.rationale,
                        "unresolved_risks": body.unresolved_risks,
                        "foundry_gate_review_id": review.id,
                        "decided_by": user.email,
                    },
                )
            except EvalClientError as exc:
                raise HTTPException(502, str(exc)) from exc
            finally:
                client.close()
            campaign_link.packet_json = json.dumps(packet)
            campaign_link.decision_status = status
            campaign_link.recommendation = decision
    if body.outcome == "advance":
        from_stage = project.stage
        transition = StageTransition(
            project_id=project.id,
            gate_review_id=review.id,
            from_stage=project.stage,
            to_stage=target_stage,
            actor_id=user.id,
        )
        db.add(transition)
        project.stage = target_stage
        if from_stage == "idea" and not project.experiments:
            dossier = project.dossier
            experiment = Experiment(
                project_id=project.id,
                question=project.hypothesis,
                method=(
                    f"Build and test: {dossier.minimum_testable_artifact}"
                    if dossier
                    else "Build the minimum testable artifact"
                ),
                acceptance_criteria=dossier.success_criteria if dossier else "",
                status="planned",
                end_date=dossier.decision_deadline if dossier else None,
            )
            db.add(experiment)
            task = Task(
                project_id=project.id,
                title="Build minimum testable artifact",
                description=experiment.method,
                status="backlog",
                position=0,
            )
            db.add(task)
            db.flush()
            db.add(
                AgentPrompt(
                    task_id=task.id,
                    title="Prepare first prototype experiment",
                    prompt_text=capture_agent_prompt_text(
                        ref=project.ref,
                        name=project.name,
                        hypothesis=project.hypothesis,
                        acceptance_criteria=experiment.acceptance_criteria,
                        form=project.form,
                        minimum_testable_artifact=(
                            dossier.minimum_testable_artifact if dossier else ""
                        ),
                    ),
                    priority=1,
                    created_by_id=user.id,
                )
            )
            if project.repo_slug:
                _provision_repo_artifact(db, project)
    elif body.outcome == "retire":
        project.status = "archived"
    db.commit()
    db.refresh(review)
    return _gate_review_out(review)


@app.get("/api/projects/{project_id}/workflow", response_model=ProjectWorkflowOut)
def project_workflow(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    blockers = _gate_blockers(db, project)
    return ProjectWorkflowOut(
        project_ref=project.ref,
        stage=project.stage,
        readiness={"can_advance": not blockers, "has_blockers": bool(blockers)},
        blockers=blockers,
        dossier=project.dossier,
        experiments=sorted(project.experiments, key=lambda row: row.created_at),
        artifacts=sorted(project.artifacts, key=lambda row: row.created_at),
        reviews=[
            _gate_review_out(row)
            for row in sorted(project.gate_reviews, key=lambda row: row.created_at)
        ],
        metrics=sorted(
            project.metric_observations,
            key=lambda row: row.observed_at,
            reverse=True,
        ),
    )


@app.post("/api/projects/{project_id}/provision-repository")
def provision_project_repository(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    uri, created = _provision_repo_artifact(db, project)
    db.commit()
    return {"project_ref": project.ref, "repository": uri, "created": created}


@app.post("/api/integrations/github/webhook")
async def github_webhook(
    request: Request,
    x_github_event: Annotated[str, Header(alias="X-GitHub-Event")],
    x_github_delivery: Annotated[str, Header(alias="X-GitHub-Delivery")],
    x_hub_signature_256: Annotated[
        str | None, Header(alias="X-Hub-Signature-256")
    ] = None,
    db: Session = Depends(get_db),
):
    raw = await request.body()
    if not settings.github_webhook_secret:
        raise HTTPException(503, "GitHub webhook secret is not configured")
    expected = "sha256=" + hmac.new(
        settings.github_webhook_secret.encode(), raw, hashlib.sha256
    ).hexdigest()
    if not x_hub_signature_256 or not hmac.compare_digest(
        expected, x_hub_signature_256
    ):
        raise HTTPException(401, "Invalid GitHub webhook signature")
    existing = (
        db.query(IntegrationEvent)
        .filter(IntegrationEvent.delivery_id == x_github_delivery)
        .first()
    )
    if existing:
        return {"status": "duplicate", "delivery_id": x_github_delivery}
    payload = json.loads(raw or b"{}")
    slug = str((payload.get("repository") or {}).get("name") or "")
    project = db.query(Project).filter(Project.repo_slug == slug).first()
    event = IntegrationEvent(
        project_id=project.id if project else None,
        provider="github",
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        payload_json=json.dumps(payload)[:100000],
    )
    db.add(event)
    if project:
        artifact_data = None
        if x_github_event == "push":
            artifact_data = {
                "kind": "commit",
                "title": f"Push {str(payload.get('after') or '')[:7]}",
                "uri": str(payload.get("compare") or ""),
                "version": str(payload.get("after") or ""),
                "commit_sha": str(payload.get("after") or ""),
                "checks_status": "pending",
            }
        elif x_github_event == "pull_request":
            pull = payload.get("pull_request") or {}
            artifact_data = {
                "kind": "pull_request",
                "title": str(pull.get("title") or "Pull request"),
                "uri": str(pull.get("html_url") or ""),
                "version": str(pull.get("head", {}).get("sha") or ""),
                "commit_sha": str(pull.get("head", {}).get("sha") or ""),
                "checks_status": (
                    "passed" if payload.get("action") == "closed" and pull.get("merged") else "pending"
                ),
            }
        elif x_github_event == "check_run":
            check = payload.get("check_run") or {}
            conclusion = str(check.get("conclusion") or "")
            artifact_data = {
                "kind": "ci_check",
                "title": str(check.get("name") or "CI check"),
                "uri": str(check.get("details_url") or ""),
                "version": str(check.get("head_sha") or ""),
                "commit_sha": str(check.get("head_sha") or ""),
                "checks_status": (
                    "passed"
                    if conclusion == "success"
                    else "failed"
                    if conclusion
                    else "pending"
                ),
            }
        elif x_github_event == "deployment_status":
            deployment = payload.get("deployment") or {}
            status_data = payload.get("deployment_status") or {}
            state = str(status_data.get("state") or "pending")
            artifact_data = {
                "kind": "deployment_preview",
                "title": f"Deployment {state}",
                "uri": str(
                    status_data.get("environment_url")
                    or status_data.get("target_url")
                    or ""
                ),
                "version": str(deployment.get("sha") or ""),
                "commit_sha": str(deployment.get("sha") or ""),
                "checks_status": "passed" if state == "success" else state,
            }
        if artifact_data and artifact_data["uri"]:
            db.add(
                Artifact(
                    project_id=project.id,
                    immutable=True,
                    **artifact_data,
                )
            )
        event.processed = True
    else:
        event.error = f"No Foundry project for repo_slug={slug}"
    db.commit()
    return {"status": "processed" if project else "unmatched", "project_ref": project.ref if project else None}


def _campaign_link_out(row: EvaluationCampaignLink) -> EvaluationCampaignLinkOut:
    packet = json.loads(row.packet_json or "{}")
    survey_url = str(packet.get("survey_url") or "")
    return EvaluationCampaignLinkOut(
        id=row.id,
        project_id=row.project_id,
        eval_campaign_id=row.eval_campaign_id,
        name=row.name,
        status=row.status,
        decision_status=row.decision_status,
        recommendation=row.recommendation,
        packet=packet,
        survey_url=survey_url,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@app.get(
    "/api/projects/{project_id}/evaluation-campaigns",
    response_model=list[EvaluationCampaignLinkOut],
)
def list_evaluation_campaigns(
    project_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    rows = (
        db.query(EvaluationCampaignLink)
        .filter(EvaluationCampaignLink.project_id == project_id)
        .order_by(EvaluationCampaignLink.created_at.desc())
        .all()
    )
    return [_campaign_link_out(row) for row in rows]


@app.post(
    "/api/projects/{project_id}/evaluation-campaigns",
    response_model=EvaluationCampaignLinkOut,
)
def start_evaluation_campaign(
    project_id: int,
    body: EvaluationCampaignRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    client = EvalClient()
    survey_url = ""
    try:
        remote = client.create_campaign(project.ref, body.model_dump())
        if normalize_form(project.form) == "physical":
            try:
                survey = client.create_survey_link(project.ref, int(remote["id"]))
                survey_url = str(survey.get("survey_url") or "")
            except EvalClientError:
                # Campaign still opens if survey minting is unavailable.
                survey_url = ""
    except EvalClientError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        client.close()
    packet = {"survey_url": survey_url} if survey_url else {}
    row = EvaluationCampaignLink(
        project_id=project.id,
        eval_campaign_id=int(remote["id"]),
        name=body.name,
        status=str(remote["status"]),
        packet_json=json.dumps(packet),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _campaign_link_out(row)


@app.post(
    "/api/projects/{project_id}/evaluation-campaigns/{link_id}/reconcile",
    response_model=EvaluationCampaignLinkOut,
)
def reconcile_evaluation_campaign(
    project_id: int,
    link_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    row = db.get(EvaluationCampaignLink, link_id)
    if not project or not row or row.project_id != project.id:
        raise HTTPException(404, "Evaluation campaign link not found")
    client = EvalClient()
    try:
        packet = client.decision_packet(project.ref, row.eval_campaign_id)
    except EvalClientError as exc:
        raise HTTPException(502, str(exc)) from exc
    finally:
        client.close()
    prior = json.loads(row.packet_json or "{}")
    if prior.get("survey_url") and not packet.get("survey_url"):
        packet["survey_url"] = prior["survey_url"]
    row.packet_json = json.dumps(packet)
    row.status = packet["campaign"]["status"]
    row.decision_status = packet["status"]
    row.recommendation = packet["recommendation"]
    if row.status == "completed":
        age = datetime.now(timezone.utc) - project.created_at.replace(
            tzinfo=timezone.utc
        )
        _record_metric_once(
            db,
            project,
            "time_to_signal",
            age.total_seconds(),
            "seconds",
            f"eval_campaign:{row.eval_campaign_id}",
        )
    db.commit()
    db.refresh(row)
    return _campaign_link_out(row)


def _release_out(row: Release) -> ReleaseOut:
    return ReleaseOut(
        id=row.id,
        project_id=row.project_id,
        artifact_id=row.artifact_id,
        version=row.version,
        target=row.target,
        rollback_reference=row.rollback_reference,
        monitoring_metric=row.monitoring_metric,
        checks=json.loads(row.checks_json or "{}"),
        status=row.status,
        approver_id=row.approver_id,
        released_at=row.released_at,
        created_at=row.created_at,
    )


@app.post(
    "/api/projects/{project_id}/deployment-adapters",
    response_model=DeploymentAdapterOut,
)
def create_deployment_adapter(
    project_id: int,
    body: DeploymentAdapterCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Project, project_id):
        raise HTTPException(404, "Project not found")
    row = DeploymentAdapter(project_id=project_id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.post("/api/projects/{project_id}/releases", response_model=ReleaseOut)
def approve_release(
    project_id: int,
    body: ReleaseCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.stage != "shipped":
        raise HTTPException(409, "Project must pass the Evaluate gate before release")
    artifact = db.get(Artifact, body.artifact_id)
    if not artifact or artifact.project_id != project.id or not artifact.immutable:
        raise HTTPException(400, "Release requires an immutable project artifact")
    required = set(required_release_checks(project.form))
    missing = sorted(key for key in required if body.checks.get(key) is not True)
    if missing:
        raise HTTPException(409, {"message": "Release gate blocked", "checks": missing})
    row = Release(
        project_id=project.id,
        artifact_id=artifact.id,
        version=body.version,
        target=body.target,
        rollback_reference=body.rollback_reference,
        monitoring_metric=body.monitoring_metric,
        checks_json=json.dumps(body.checks),
        status="approved",
        approver_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _release_out(row)


@app.post(
    "/api/releases/{release_id}/deploy/{adapter_id}",
    response_model=DeploymentRunOut,
)
def deploy_release(
    release_id: int,
    adapter_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    release = db.get(Release, release_id)
    adapter = db.get(DeploymentAdapter, adapter_id)
    if (
        not release
        or not adapter
        or adapter.project_id != release.project_id
        or not adapter.active
    ):
        raise HTTPException(404, "Release or deployment adapter not found")
    run = DeploymentRun(
        release_id=release.id,
        adapter_id=adapter.id,
        status="running",
        health_status="unknown",
    )
    db.add(run)
    db.flush()
    try:
        if adapter.kind == "portfolio":
            result = _site_deploy_or_http_error(db)
            run.output = result.stdout[-10000:]
            success = result.success
        else:
            import httpx

            if adapter.kind == "webhook":
                response = httpx.post(
                    adapter.target_url,
                    json={
                        "project_id": release.project_id,
                        "release_id": release.id,
                        "artifact_id": release.artifact_id,
                        "version": release.version,
                        "target": release.target,
                        "rollback_reference": release.rollback_reference,
                    },
                    timeout=60,
                )
            else:
                response = httpx.get(adapter.target_url or release.target, timeout=20)
            success = response.status_code < 400
            run.output = f"Health check HTTP {response.status_code}"
        run.status = "completed" if success else "failed"
        run.health_status = "healthy" if success else "unhealthy"
        if success:
            release.status = "released"
            release.released_at = datetime.now(timezone.utc)
    except Exception as exc:
        run.status = "failed"
        run.health_status = "unhealthy"
        run.output = str(exc)
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return run


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
    if body.external_key:
        existing = (
            db.query(Task).filter(Task.external_key == body.external_key).first()
        )
        if existing:
            if existing.project_id != project_id:
                raise HTTPException(409, "external_key belongs to another project")
            return existing
    max_pos = (
        db.query(Task)
        .filter(Task.project_id == project_id, Task.status == body.status)
        .count()
    )
    task = Task(
        project_id=project_id,
        title=body.title,
        external_key=body.external_key,
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


@app.post("/api/agent-prompts/claim", response_model=AgentPromptClaimOut | None)
def claim_prompt(
    body: AgentClaimRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    now = datetime.now(timezone.utc)
    available = or_(
        AgentPrompt.status == "pending",
        (AgentPrompt.status == "in_progress")
        & (AgentPrompt.lease_expires_at < now),
    )
    candidate = (
        db.query(AgentPrompt)
        .filter(available)
        .order_by(AgentPrompt.priority.desc(), AgentPrompt.created_at)
        .first()
    )
    if candidate is None:
        return None
    lease_token = secrets.token_urlsafe(32)
    updated = (
        db.query(AgentPrompt)
        .filter(AgentPrompt.id == candidate.id, available)
        .update(
            {
                AgentPrompt.status: "in_progress",
                AgentPrompt.worker_id: body.worker_id,
                AgentPrompt.lease_token: lease_token,
                AgentPrompt.lease_expires_at: now
                + timedelta(seconds=body.lease_seconds),
                AgentPrompt.heartbeat_at: now,
                AgentPrompt.attempts: AgentPrompt.attempts + 1,
                AgentPrompt.error: "",
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.rollback()
        return None
    db.flush()
    prompt = db.get(AgentPrompt, candidate.id, populate_existing=True)
    assert prompt is not None
    prompt.task.status = "doing"
    db.commit()
    return AgentPromptClaimOut(
        **prompt_out(prompt, db).model_dump(),
        lease_token=prompt.lease_token,
    )


def _leased_prompt(
    db: Session, prompt_id: int, worker_id: str, lease_token: str
) -> AgentPrompt:
    prompt = db.get(AgentPrompt, prompt_id)
    if not prompt:
        raise HTTPException(404, "Agent prompt not found")
    if prompt.status in ("completed", "failed", "cancelled"):
        return prompt
    if prompt.worker_id != worker_id or not secrets.compare_digest(
        prompt.lease_token or "", lease_token
    ):
        raise HTTPException(409, "Worker does not hold this prompt lease")
    return prompt


@app.post("/api/agent-prompts/{prompt_id}/heartbeat", response_model=AgentPromptOut)
def heartbeat_prompt(
    prompt_id: int,
    body: AgentHeartbeatRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    prompt = _leased_prompt(db, prompt_id, body.worker_id, body.lease_token)
    if prompt.status == "in_progress":
        now = datetime.now(timezone.utc)
        prompt.heartbeat_at = now
        prompt.lease_expires_at = now + timedelta(seconds=body.lease_seconds)
        db.commit()
        db.refresh(prompt)
    return prompt_out(prompt, db)


@app.post("/api/agent-prompts/{prompt_id}/complete", response_model=AgentPromptOut)
def complete_prompt(
    prompt_id: int,
    body: AgentCompleteRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    prompt = _leased_prompt(db, prompt_id, body.worker_id, body.lease_token)
    if prompt.status in ("completed", "failed", "cancelled"):
        return prompt_out(prompt, db)
    prompt.result_json = json.dumps(body.result)
    prompt.result_notes = body.result_notes
    prompt.runtime_seconds = body.runtime_seconds
    prompt.cost_usd = body.cost_usd
    prompt.artifact_refs_json = json.dumps(body.artifact_refs)
    if body.runtime_seconds is not None:
        db.add(
            MetricObservation(
                project_id=prompt.task.project_id,
                key="agent_runtime",
                value=body.runtime_seconds,
                unit="seconds",
                source=f"agent_prompt:{prompt.id}",
            )
        )
    if body.cost_usd is not None:
        db.add(
            MetricObservation(
                project_id=prompt.task.project_id,
                key="agent_cost",
                value=body.cost_usd,
                unit="USD",
                source=f"agent_prompt:{prompt.id}",
            )
        )
    prompt.lease_token = ""
    prompt.lease_expires_at = None
    if body.success:
        prompt.status = "completed"
        prompt.error = ""
        prompt.task.status = "testing"
    elif prompt.attempts < 3:
        prompt.status = "pending"
        prompt.error = body.error
    else:
        prompt.status = "failed"
        prompt.error = body.error
    db.commit()
    db.refresh(prompt)
    return prompt_out(prompt, db)


@app.post("/api/agent-prompts", response_model=AgentPromptOut, status_code=201)
def create_prompt(
    body: AgentPromptCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if not db.get(Task, body.task_id):
        raise HTTPException(404, "Task not found")
    if body.external_key:
        existing = (
            db.query(AgentPrompt)
            .filter(AgentPrompt.external_key == body.external_key)
            .first()
        )
        if existing:
            if existing.task_id != body.task_id:
                raise HTTPException(409, "external_key belongs to another task")
            return prompt_out(existing, db)
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

if eval_app:
    app.mount("/eval", eval_app, name="foundry-eval")

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
