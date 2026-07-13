from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


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


class ProjectCreate(BaseModel):
    ref: str = Field(min_length=2, max_length=32, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=1, max_length=255)
    hypothesis: str = ""
    form: str = "interactive"
    stage: str = "idea"
    visibility: str = "public"
    repo_slug: str = Field(default="", max_length=47, pattern=r"^$|^[a-z][a-z0-9-]{1,46}$")


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    hypothesis: str | None = None
    form: str | None = None
    stage: str | None = None
    status: str | None = None
    visibility: str | None = None
    repo_slug: str | None = Field(
        default=None, max_length=47, pattern=r"^$|^[a-z][a-z0-9-]{1,46}$"
    )


class ProjectOut(BaseModel):
    id: int
    ref: str
    name: str
    hypothesis: str
    form: str
    stage: str
    status: str
    visibility: str = "public"
    repo_slug: str = ""
    owner_id: int
    created_at: datetime
    updated_at: datetime
    task_counts: dict[str, int] = {}
    can_deploy_site: bool = False

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


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    position: int | None = None


class TaskOut(BaseModel):
    id: int
    project_id: int
    title: str
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
    prompt_text: str
    status: str
    priority: int
    result_notes: str
    created_by_id: int
    created_at: datetime
    updated_at: datetime
    task_title: str | None = None
    project_ref: str | None = None

    model_config = {"from_attributes": True}
