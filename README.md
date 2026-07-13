# Perrin Research Foundry

Internal project tracker, lightweight kanban, and agent prompt queue — companion to the public portfolio site.

## Components

| Path | Description |
|------|-------------|
| `backend/` | FastAPI + SQLite API |
| `web/` | Internal web UI (foundry styling) |
| `android/` | Kotlin Compose companion app |

## Quick start

**Option A — Python (recommended if venv setup is incomplete):**
```bash
cd foundry
pip install -r backend/requirements.txt
python3 run.py
```

**Option B — Shell script (do not run with `python`):**
```bash
cd foundry
chmod +x scripts/run.sh
./scripts/run.sh
```

Open http://localhost:8000

**If `./scripts/run.sh` fails with "uvicorn: No such file or directory":** your `venv/` is incomplete (common when `python3-venv` is not installed). Either:

```bash
# Use system/user Python (works now if you ran pip install -r backend/requirements.txt)
python3 run.py

# Or recreate venv (requires: apt install python3.10-venv)
rm -rf venv
python3 -m venv venv
venv/bin/pip install -r backend/requirements.txt
./scripts/run.sh
```

**Demo login:** `scott@perrinresearch.com` / `foundry-demo` (bootstrapped as admin)

## API

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/login` | JWT login (rejects revoked accounts) |
| `POST /api/auth/register` | Closed — returns 403; admins create users |
| `GET /api/auth/me` | Current user (`is_admin`, `is_active`) |
| `POST /api/auth/change-password` | Change own password (`current_password`, `new_password`) |
| `GET /api/users` | List users (admin) |
| `POST /api/users` | Create user (admin) |
| `PATCH /api/users/{id}` | Update admin/active flags or set temp password (admin) |
| `GET /api/projects` | List projects |
| `POST /api/projects` | Create project |
| `PATCH /api/projects/{id}` | Update project (stage, status, visibility, repo_slug, etc.) |
| `POST /api/site/deploy` | Sync active portfolio projects and publish public site |
| `POST /api/projects/{id}/deploy-site` | Legacy deploy endpoint (PR-000 only; prefer `/api/site/deploy`) |
| `GET /api/projects/{id}/tasks` | Kanban tasks |
| `PATCH /api/tasks/{id}` | Move task column |
| `GET /api/agent-prompts` | Agent prompt queue (`?project_id=` or `?task_id=`) |
| `GET /api/tasks/{id}/agent-prompts` | Prompts for a task |
| `GET /api/agent-prompts/pending` | Pending prompts for agents |
| `POST /api/agent-prompts` | Submit agent prompt (`task_id` required) |
| `POST /api/agent-prompts/reorder` | Reorder queue (`ordered_ids` top to bottom) |
| `PATCH /api/agent-prompts/{id}` | Update agent prompt |
| `DELETE /api/agent-prompts/{id}` | Delete agent prompt |

## User management

- Public registration is closed. Admins create accounts from the **Users** tab.
- Any signed-in user can **Change password** from the header.
- Admins can set a temporary password, promote/demote admins, and revoke/restore access.
- The first user (preferring `scott@perrinresearch.com`) is bootstrapped as admin on startup if no admin exists.

## Android

Open `android/` in Android Studio. Set `API_BASE_URL` in `app/build.gradle.kts` to your server (default: `https://foundry.perrinresearch.com`).

For local dev against emulator: `http://10.0.2.2:8000`

## Environment

| Variable | Default |
|----------|---------|
| `FOUNDRY_SECRET_KEY` | change-me-in-production |
| `FOUNDRY_PORT` | 8411 |
| `FOUNDRY_CORS_ORIGINS` | localhost origins |
| `FOUNDRY_SITE_DEPLOY_SCRIPT` | `.../dev.perrinresearch.com/site/scripts/deploy.sh` |
| `FOUNDRY_SITE_PUBLIC_URL` | `https://dev.perrinresearch.com` |
| `FOUNDRY_SITE_PUBLIC_DIR` | `.../dev.perrinresearch.com/public` |

## Site deploy

From the Foundry UI, open **Projects** and click **Publish public site**. This syncs **active, public** pipeline projects into the public portfolio (creating new entries when needed, removing private/archived ones), runs the Astro build, and rsyncs to the public docroot (currently dev.perrinresearch.com; set `FOUNDRY_SITE_PUBLIC_URL` when moving to perrinresearch.com).

Set a project's **Visibility** to **Private** to keep it in Foundry without showing it on the public site.

## Deployment (planned)

Mirror Waypoint: subdomain `foundry.perrinresearch.com` with Passenger + `a2wsgi` serving the FastAPI app and static web UI.
