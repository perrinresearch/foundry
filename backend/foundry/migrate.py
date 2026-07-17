"""One-off SQLite migrations for Foundry schema changes."""

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def migrate_agent_prompts_to_tasks(engine: Engine) -> None:
    """Move agent_prompts.project_id → task_id (assign to first task per project)."""
    insp = inspect(engine)
    if "agent_prompts" not in insp.get_table_names():
        return

    cols = {c["name"] for c in insp.get_columns("agent_prompts")}
    if "task_id" in cols:
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE agent_prompts_new (
                    id INTEGER NOT NULL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id),
                    title VARCHAR(255) NOT NULL,
                    prompt_text TEXT NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'pending',
                    priority INTEGER NOT NULL DEFAULT 0,
                    result_notes TEXT NOT NULL DEFAULT '',
                    created_by_id INTEGER NOT NULL REFERENCES users(id),
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO agent_prompts_new (
                    id, task_id, title, prompt_text, status, priority,
                    result_notes, created_by_id, created_at, updated_at
                )
                SELECT
                    p.id,
                    COALESCE(
                        (
                            SELECT t.id FROM tasks t
                            WHERE t.project_id = p.project_id
                            ORDER BY t.position, t.id
                            LIMIT 1
                        ),
                        (SELECT id FROM tasks ORDER BY id LIMIT 1)
                    ),
                    p.title,
                    p.prompt_text,
                    p.status,
                    p.priority,
                    p.result_notes,
                    p.created_by_id,
                    p.created_at,
                    p.updated_at
                FROM agent_prompts p
                """
            )
        )
        conn.execute(text("DROP TABLE agent_prompts"))
        conn.execute(text("ALTER TABLE agent_prompts_new RENAME TO agent_prompts"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agent_prompts_task_id ON agent_prompts (task_id)")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_agent_prompts_status ON agent_prompts (status)")
        )


def migrate_task_statuses(engine: Engine) -> None:
    """Merge legacy todo into backlog; drop todo from active statuses."""
    insp = inspect(engine)
    if "tasks" not in insp.get_table_names():
        return
    with engine.begin() as conn:
        conn.execute(text("UPDATE tasks SET status = 'backlog' WHERE status = 'todo'"))


def migrate_project_visibility(engine: Engine) -> None:
    """Add projects.visibility (public|private); existing rows default to public."""
    insp = inspect(engine)
    if "projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("projects")}
    if "visibility" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE projects ADD COLUMN visibility VARCHAR(32) NOT NULL DEFAULT 'public'"
            )
        )


def migrate_project_repo_slug(engine: Engine) -> None:
    """Add projects.repo_slug for local WSL GitHub provision (empty = no repo)."""
    insp = inspect(engine)
    if "projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("projects")}
    if "repo_slug" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE projects ADD COLUMN repo_slug VARCHAR(47) NOT NULL DEFAULT ''"
            )
        )


def migrate_user_admin_flags(engine: Engine) -> None:
    """Add users.is_admin and users.is_active for access control."""
    insp = inspect(engine)
    if "users" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "is_admin" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0")
            )
        if "is_active" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )


def migrate_project_customer(engine: Engine) -> None:
    """Add projects.customer (customer / requestor label)."""
    insp = inspect(engine)
    if "projects" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("projects")}
    if "customer" in cols:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE projects ADD COLUMN customer VARCHAR(255) NOT NULL DEFAULT ''"
            )
        )
