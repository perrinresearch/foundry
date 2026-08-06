"""Seed demo user and portfolio projects."""

from sqlalchemy.orm import Session

from foundry.auth import hash_password
from foundry.models import AgentPrompt, Project, Task, User

PR000 = {
    "ref": "PR-000",
    "name": "Perrin Research",
    "hypothesis": "A public site that explains the foundry operating model and pipeline can attract collaborators and validate the portfolio thesis.",
    "form": "interactive",
    "stage": "shipped",
    "tasks": [
        ("Align foundry internal UI with public branding", "done"),
        ("Add PR-000 deploy-from-foundry workflow", "doing"),
        ("Point production DNS at perrinresearch.com", "backlog"),
    ],
}

SEED_PROJECTS = [
    PR000,
    {
        "ref": "PR-001",
        "name": "Restore79",
        "hypothesis": "Dystrophin and muscle models plus financial disease-cost models can change how Duchenne therapies are valued.",
        "form": "interactive",
        "stage": "prototype",
        "tasks": [
            (
                "Wire dystrophin model to cost API",
                "doing",
                [
                    (
                        "Summarize Restore79 model assumptions",
                        "Review the Restore79 dystrophin model and list the top 5 assumptions that would most affect a payer's valuation. Output as bullet points.",
                    ),
                ],
            ),
            ("Validate against published cohort data", "backlog"),
            ("Draft investor-facing summary", "backlog"),
        ],
    },
    {
        "ref": "PR-002",
        "name": "Waypoint",
        "hypothesis": "Portfolio surveillance focused on a sector or disease area surfaces where capital and science converge before the market does.",
        "form": "interactive",
        "stage": "prototype",
        "tasks": [
            (
                "Add DMD pipeline milestone alerts",
                "doing",
                [
                    (
                        "Scan DMD trial landscape",
                        "Using Waypoint's DMD portfolio, identify any trials that changed phase in the last 30 days and summarize implications for Restore79.",
                    ),
                ],
            ),
            ("Tune landscape scoring weights", "backlog"),
            ("Export weekly digest template", "backlog"),
        ],
    },
    {
        "ref": "PR-003",
        "name": "ScholarWeave",
        "hypothesis": "Connecting scientific literature as a graph reveals relationships that keyword search structurally misses.",
        "form": "interactive",
        "stage": "idea",
        "tasks": [
            ("Define citation graph schema", "backlog"),
            ("Prototype PubMed ingest", "backlog"),
        ],
    },
    {
        "ref": "PR-004",
        "name": "Leading with Attention",
        "hypothesis": "Lessons from AI software engineering translate directly into how technical teams should be led.",
        "form": "static",
        "stage": "shipped",
        "tasks": [
            ("Outline next essay in series", "backlog"),
        ],
    },
    {
        "ref": "PR-005",
        "name": "Train or Detrain",
        "hypothesis": "Families navigating Duchenne need a clear, evidence-based account of muscle, exercise, and plasticity.",
        "form": "static",
        "stage": "evaluation",
        "tasks": [
            ("Review draft chapters for clinical accuracy", "doing"),
            ("Gather caregiver feedback on key sections", "testing"),
            ("Finalize publication outline", "backlog"),
        ],
    },
    {
        "ref": "PR-006",
        "name": "Built to Change",
        "hypothesis": "Gaming muscle plasticity for lasting mobility is a book-scale idea — too big for a post, too useful to stay unwritten.",
        "form": "static",
        "stage": "prototype",
        "tasks": [
            ("Draft chapter on muscle plasticity basics", "doing"),
            ("Outline remaining book structure", "backlog"),
            ("Prototype exercise progression framework", "backlog"),
        ],
    },
    {
        "ref": "PR-007",
        "name": "Physical mockup pilot",
        "hypothesis": (
            "A mockup-first physical product package (diagrams and renderings) can "
            "test whether claimed user value justifies the next build-cost increment."
        ),
        "form": "physical",
        "stage": "idea",
        "tasks": [
            ("Assemble design diagram and rendering package", "backlog"),
            ("Define value claims and rough build-cost band", "backlog"),
        ],
    },
]


def _add_task_prompts(db: Session, task_id: int, prompts: list, owner_id: int, priority: int) -> None:
    for title, prompt_text in prompts:
        db.add(
            AgentPrompt(
                task_id=task_id,
                title=title,
                prompt_text=prompt_text,
                created_by_id=owner_id,
                priority=priority,
            )
        )


def _create_project_with_tasks(
    db: Session, pdata: dict, owner_id: int, priority_base: int
) -> None:
    project = Project(
        ref=pdata["ref"],
        name=pdata["name"],
        hypothesis=pdata["hypothesis"],
        form=pdata["form"],
        stage=pdata["stage"],
        owner_id=owner_id,
    )
    db.add(project)
    db.flush()

    for j, task_data in enumerate(pdata.get("tasks", [])):
        if len(task_data) == 2:
            title, status = task_data
            task_prompts: list = []
        else:
            title, status, task_prompts = task_data
        task = Task(
            project_id=project.id,
            title=title,
            status=status,
            position=j,
        )
        db.add(task)
        db.flush()
        _add_task_prompts(db, task.id, task_prompts, owner_id, priority_base)


def ensure_seed_projects(db: Session) -> None:
    """Add any seed projects missing from an existing database."""
    user = db.query(User).first()
    if not user:
        return
    existing_refs = {p.ref for p in db.query(Project.ref).all()}
    for i, pdata in enumerate(SEED_PROJECTS):
        if pdata["ref"] in existing_refs:
            continue
        _create_project_with_tasks(db, pdata, user.id, 10 - i)
    db.commit()


def ensure_bootstrap_admin(db: Session) -> None:
    """Ensure at least one admin exists (prefer scott@perrinresearch.com)."""
    if db.query(User).filter(User.is_admin == True).first():  # noqa: E712
        return
    preferred = (
        db.query(User).filter(User.email == "scott@perrinresearch.com").first()
    )
    user = preferred or db.query(User).order_by(User.id).first()
    if not user:
        return
    user.is_admin = True
    user.is_active = True
    db.commit()


def seed_database(db: Session) -> None:
    if db.query(User).first():
        ensure_seed_projects(db)
        ensure_bootstrap_admin(db)
        return

    user = User(
        email="scott@perrinresearch.com",
        name="Scott Perrin",
        password_hash=hash_password("foundry-demo"),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.flush()

    for i, pdata in enumerate(SEED_PROJECTS):
        _create_project_with_tasks(db, pdata, user.id, 10 - i)

    db.commit()
    ensure_bootstrap_admin(db)
