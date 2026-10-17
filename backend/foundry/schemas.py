from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from foundry.forms import PROJECT_FORMS


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    name: str
    is_admin: bool = False
    is_active: bool = True
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class AdminUserCreate(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
    is_admin: bool = False


class AdminUserUpdate(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)
    name: str | None = Field(default=None, min_length=1, max_length=255)

# GitHub repository names: ASCII alphanumerics, hyphens, underscores, periods.
# Blank = no local provision by project_sync. Max 100 chars (GitHub limit).
REPO_SLUG_PATTERN = r"^$|^[A-Za-z0-9._-]{1,100}$"


def normalize_repo_slug(value: str | None) -> str | None:
    if value is None:
        return None
    slug = value.strip()
    if not slug:
        return ""
    if slug.startswith("-"):
        raise ValueError("GitHub repo names cannot start with a hyphen")
    if slug.lower().endswith(".git"):
        raise ValueError("GitHub repo names cannot end with .git")
    if slug in (".", ".."):
        raise ValueError("GitHub repo names cannot be '.' or '..'")
    return slug


class ProjectCreate(BaseModel):
    ref: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    hypothesis: str = ""
    customer: str = Field(default="", max_length=255)
    form: str = Field(default="interactive", pattern=r"^(interactive|static|physical)$")
    stage: str = "idea"
    priority: str = "normal"
    visibility: str = "public"
    repo_slug: str = Field(default="", max_length=100, pattern=REPO_SLUG_PATTERN)

    @field_validator("form")
    @classmethod
    def validate_form(cls, value: str) -> str:
        form = (value or "").strip().lower()
        if form not in PROJECT_FORMS:
            raise ValueError(f"form must be one of: {', '.join(PROJECT_FORMS)}")
        return form

    @field_validator("repo_slug")
    @classmethod
    def validate_repo_slug(cls, value: str) -> str:
        return normalize_repo_slug(value) or ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hypothesis: str | None = None
    customer: str | None = Field(default=None, max_length=255)
    form: str | None = Field(
        default=None, pattern=r"^(interactive|static|physical)$"
    )
    stage: str | None = None
    status: str | None = None
    priority: str | None = None
    visibility: str | None = None
    repo_slug: str | None = Field(
        default=None, max_length=100, pattern=REPO_SLUG_PATTERN
    )

    @field_validator("form")
    @classmethod
    def validate_form(cls, value: str | None) -> str | None:
        if value is None:
            return None
        form = value.strip().lower()
        if form not in PROJECT_FORMS:
            raise ValueError(f"form must be one of: {', '.join(PROJECT_FORMS)}")
        return form

    @field_validator("repo_slug")
    @classmethod
    def validate_repo_slug(cls, value: str | None) -> str | None:
        return normalize_repo_slug(value)


class ProjectOut(BaseModel):
    id: int
    ref: str
    name: str
    hypothesis: str
    customer: str = ""
    form: str
    stage: str
    status: str
    priority: str = "normal"
    visibility: str = "public"
    repo_slug: str = ""
    owner_id: int
    created_at: datetime
    updated_at: datetime
    task_counts: dict[str, int] = {}
    can_deploy_site: bool = False
    gate_blockers: list[str] = []
    evidence_coverage: float = 0.0

    model_config = {"from_attributes": True}


class ProjectDossierUpsert(BaseModel):
    observable_problem: str = ""
    expected_value: str = ""
    falsification_condition: str = ""
    domain: str = Field(default="", max_length=128)
    decision_deadline: datetime | None = None
    initial_evidence: str = ""
    minimum_testable_artifact: str = ""
    success_criteria: str = ""


class ProjectDossierOut(ProjectDossierUpsert):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ExperimentCreate(BaseModel):
    question: str = Field(min_length=1)
    method: str = ""
    acceptance_criteria: str = ""
    status: str = "planned"
    end_date: datetime | None = None


class ExperimentUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=1)
    method: str | None = None
    acceptance_criteria: str | None = None
    status: str | None = None
    end_date: datetime | None = None


class ExperimentOut(ExperimentCreate):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


class ArtifactCreate(BaseModel):
    experiment_id: int | None = None
    kind: str = Field(default="other", max_length=64)
    title: str = Field(min_length=1, max_length=255)
    uri: str = Field(min_length=1)
    version: str = Field(default="", max_length=255)
    commit_sha: str = Field(default="", max_length=64)
    checks_status: str = Field(default="pending", max_length=32)
    immutable: bool = True


class ArtifactOut(ArtifactCreate):
    id: int
    project_id: int
    created_at: datetime
    model_config = {"from_attributes": True}


class GateReviewCreate(BaseModel):
    outcome: str = Field(pattern=r"^(advance|iterate|hold|retire)$")
    rationale: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    unresolved_risks: str = ""
    next_action: str = ""
    policy_version: str = "1.0"
    wip_override: bool = False


class GateReviewOut(BaseModel):
    id: int
    project_id: int
    reviewer_id: int
    from_stage: str
    target_stage: str
    outcome: str
    policy_version: str
    rationale: str
    evidence_refs: list[str]
    unresolved_risks: str
    next_action: str
    wip_override: bool
    created_at: datetime


class MetricObservationCreate(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    value: float
    unit: str = Field(default="", max_length=64)
    source: str = Field(default="", max_length=255)
    observed_at: datetime | None = None


class MetricObservationOut(MetricObservationCreate):
    id: int
    project_id: int
    observed_at: datetime
    created_at: datetime
    model_config = {"from_attributes": True}


class ProjectWorkflowOut(BaseModel):
    project_ref: str
    stage: str
    policy_version: str = "1.0"
    readiness: dict[str, bool]
    blockers: list[str]
    dossier: ProjectDossierOut | None
    experiments: list[ExperimentOut]
    artifacts: list[ArtifactOut]
    reviews: list[GateReviewOut]
    metrics: list[MetricObservationOut]


class EvaluationCampaignRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    claim: str = Field(min_length=1)
    artifact_refs: list[str] = Field(min_length=1)
    audience: str = ""
    sample_target: int = Field(default=3, ge=1)
    min_human_samples: int = Field(default=1, ge=0)
    success_threshold: float = Field(default=0.75, ge=0, le=1)
    status: str = "open"


class EvaluationCampaignLinkOut(BaseModel):
    id: int
    project_id: int
    eval_campaign_id: int
    name: str
    status: str
    decision_status: str
    recommendation: str
    packet: dict
    survey_url: str = ""
    created_at: datetime
    updated_at: datetime


class ReleaseCreate(BaseModel):
    artifact_id: int
    version: str = Field(min_length=1, max_length=255)
    target: str = Field(min_length=1, max_length=512)
    rollback_reference: str = Field(min_length=1)
    monitoring_metric: str = Field(min_length=1, max_length=128)
    checks: dict[str, bool]


class ReleaseOut(BaseModel):
    id: int
    project_id: int
    artifact_id: int
    version: str
    target: str
    rollback_reference: str
    monitoring_metric: str
    checks: dict[str, bool]
    status: str
    approver_id: int
    released_at: datetime | None
    created_at: datetime


class DeploymentAdapterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(
        default="external", pattern=r"^(portfolio|webhook|external|static)$"
    )
    target_url: str = ""


class DeploymentAdapterOut(DeploymentAdapterCreate):
    id: int
    project_id: int
    active: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class DeploymentRunOut(BaseModel):
    id: int
    release_id: int
    adapter_id: int
    status: str
    health_status: str
    output: str
    started_at: datetime
    completed_at: datetime | None
    model_config = {"from_attributes": True}


class SiteDeployOut(BaseModel):
    success: bool
    message: str
    stdout: str
    stderr: str
    exit_code: int
    target_url: str
    public_dir: str
    synced_refs: list[str] = []


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    status: str = "backlog"
    external_key: str | None = Field(default=None, max_length=255)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    position: int | None = None


class TaskOut(BaseModel):
    id: int
    project_id: int
    title: str
    external_key: str | None = None
    description: str
    status: str
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentPromptCreate(BaseModel):
    task_id: int
    title: str = Field(min_length=1, max_length=255)
    prompt_text: str = Field(min_length=1)
    priority: int = 0
    external_key: str | None = Field(default=None, max_length=255)


class AgentPromptUpdate(BaseModel):
    title: str | None = None
    prompt_text: str | None = None
    status: str | None = None
    priority: int | None = None
    result_notes: str | None = None


class AgentPromptReorder(BaseModel):
    ordered_ids: list[int] = Field(min_length=1)


class AgentPromptOut(BaseModel):
    id: int
    task_id: int
    title: str
    external_key: str | None = None
    prompt_text: str
    status: str
    priority: int
    result_notes: str
    result_json: dict = {}
    error: str = ""
    worker_id: str = ""
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    attempts: int = 0
    runtime_seconds: float | None = None
    cost_usd: float | None = None
    artifact_refs: list[str] = []
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    task_title: str | None = None
    project_ref: str | None = None
    repo_slug: str = ""
    repo_cwd: str = ""

    model_config = {"from_attributes": True}


class AgentPromptClaimOut(AgentPromptOut):
    lease_token: str


class AgentClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_seconds: int = Field(default=900, ge=60, le=3600)


class AgentHeartbeatRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: str = Field(min_length=1)
    lease_seconds: int = Field(default=900, ge=60, le=3600)


class AgentCompleteRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=255)
    lease_token: str = Field(min_length=1)
    success: bool
    result: dict = {}
    result_notes: str = ""
    error: str = ""
    runtime_seconds: float | None = Field(default=None, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    artifact_refs: list[str] = []


class GitHubRepoOut(BaseModel):
    name: str
    private: bool = True
    html_url: str = ""
    default_branch: str = "main"
    updated_at: str = ""


class GitHubForkRequest(BaseModel):
    source: str = Field(
        min_length=3,
        max_length=255,
        description="Source repository as owner/repo",
    )
    name: str | None = Field(
        default=None,
        max_length=100,
        pattern=REPO_SLUG_PATTERN,
        description="Optional target repo name under FOUNDRY_GITHUB_ORG",
    )

    @field_validator("source")
    @classmethod
    def validate_source(cls, value: str) -> str:
        raw = (value or "").strip().removesuffix(".git")
        if raw.count("/") != 1:
            raise ValueError("source must be owner/repo")
        owner, repo = raw.split("/", 1)
        owner = owner.strip()
        repo = repo.strip()
        if not owner or not repo:
            raise ValueError("source must be owner/repo")
        if owner.startswith("-") or repo.startswith("-"):
            raise ValueError("GitHub names cannot start with a hyphen")
        return f"{owner}/{repo}"

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_repo_slug(value) or None


class GitHubForkOut(BaseModel):
    repo_slug: str
    html_url: str
    default_branch: str = "main"
