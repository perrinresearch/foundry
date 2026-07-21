from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from foundry.database import Base

TASK_STATUSES = ("backlog", "doing", "testing", "done")
AGENT_STATUSES = ("pending", "in_progress", "completed", "failed", "cancelled")
PROJECT_STAGES = ("idea", "prototype", "evaluation", "shipped")
PROJECT_STATUSES = ("active", "archived")
PROJECT_VISIBILITIES = ("public", "private")
PROJECT_PRIORITIES = ("critical", "high", "normal", "low")
GATE_OUTCOMES = ("advance", "iterate", "hold", "retire")
EXPERIMENT_STATUSES = ("planned", "running", "completed", "cancelled")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner")
    agent_prompts: Mapped[list["AgentPrompt"]] = relationship(back_populates="creator")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ref: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    customer: Mapped[str] = mapped_column(String(255), default="")
    form: Mapped[str] = mapped_column(String(32), default="interactive")
    stage: Mapped[str] = mapped_column(String(32), default="idea")
    status: Mapped[str] = mapped_column(String(32), default="active")
    visibility: Mapped[str] = mapped_column(String(32), default="public")
    priority: Mapped[str] = mapped_column(String(32), default="normal")
    # Optional GitHub/local folder name; empty = Foundry-only (no local provision)
    repo_slug: Mapped[str] = mapped_column(String(47), default="")
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    owner: Mapped["User"] = relationship(back_populates="projects")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Task.position"
    )
    dossier: Mapped["ProjectDossier | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    gate_reviews: Mapped[list["GateReview"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    metric_observations: Mapped[list["MetricObservation"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    evaluation_campaigns: Mapped[list["EvaluationCampaignLink"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    releases: Mapped[list["Release"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    deployment_adapters: Mapped[list["DeploymentAdapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectDossier(Base):
    __tablename__ = "project_dossiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), unique=True, index=True
    )
    observable_problem: Mapped[str] = mapped_column(Text, default="")
    expected_value: Mapped[str] = mapped_column(Text, default="")
    falsification_condition: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String(128), default="")
    decision_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    initial_evidence: Mapped[str] = mapped_column(Text, default="")
    minimum_testable_artifact: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="dossier")


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planned", index=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="experiments")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="experiment")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    experiment_id: Mapped[int | None] = mapped_column(
        ForeignKey("experiments.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64), default="other")
    title: Mapped[str] = mapped_column(String(255))
    uri: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(255), default="")
    commit_sha: Mapped[str] = mapped_column(String(64), default="")
    checks_status: Mapped[str] = mapped_column(String(32), default="pending")
    immutable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="artifacts")
    experiment: Mapped["Experiment | None"] = relationship(back_populates="artifacts")


class GateReview(Base):
    __tablename__ = "gate_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    from_stage: Mapped[str] = mapped_column(String(32))
    target_stage: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(32), index=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="1.0")
    rationale: Mapped[str] = mapped_column(Text)
    evidence_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    unresolved_risks: Mapped[str] = mapped_column(Text, default="")
    next_action: Mapped[str] = mapped_column(Text, default="")
    wip_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="gate_reviews")
    transition: Mapped["StageTransition | None"] = relationship(
        back_populates="gate_review", cascade="all, delete-orphan", uselist=False
    )


class StageTransition(Base):
    __tablename__ = "stage_transitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    gate_review_id: Mapped[int] = mapped_column(
        ForeignKey("gate_reviews.id"), unique=True, index=True
    )
    from_stage: Mapped[str] = mapped_column(String(32))
    to_stage: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    gate_review: Mapped["GateReview"] = relationship(back_populates="transition")


class MetricObservation(Base):
    __tablename__ = "metric_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(64), default="")
    source: Mapped[str] = mapped_column(String(255), default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="metric_observations")


class EvaluationCampaignLink(Base):
    __tablename__ = "evaluation_campaign_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    eval_campaign_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="planned")
    decision_status: Mapped[str] = mapped_column(String(32), default="pending")
    recommendation: Mapped[str] = mapped_column(String(32), default="")
    packet_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="evaluation_campaigns")


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("artifacts.id"))
    version: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(512))
    rollback_reference: Mapped[str] = mapped_column(Text)
    monitoring_metric: Mapped[str] = mapped_column(String(128))
    checks_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="releases")


class DeploymentAdapter(Base):
    __tablename__ = "deployment_adapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(32), default="external")
    target_url: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="deployment_adapters")


class DeploymentRun(Base):
    __tablename__ = "deployment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id"), index=True)
    adapter_id: Mapped[int] = mapped_column(ForeignKey("deployment_adapters.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    health_status: Mapped[str] = mapped_column(String(32), default="unknown")
    output: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    delivery_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    external_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="backlog", index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    project: Mapped["Project"] = relationship(back_populates="tasks")
    agent_prompts: Mapped[list["AgentPrompt"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class AgentPrompt(Base):
    __tablename__ = "agent_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    external_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    prompt_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    result_notes: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str] = mapped_column(Text, default="")
    worker_id: Mapped[str] = mapped_column(String(255), default="")
    lease_token: Mapped[str] = mapped_column(String(128), default="")
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    artifact_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    task: Mapped["Task"] = relationship(back_populates="agent_prompts")
    creator: Mapped["User"] = relationship(back_populates="agent_prompts")
