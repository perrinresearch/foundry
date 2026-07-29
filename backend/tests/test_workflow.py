from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from foundry.auth import hash_password
from foundry.database import Base, get_db
from foundry.models import (
    AgentPrompt,
    EvaluationCampaignLink,
    Project,
    StageTransition,
    User,
)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(session):
    from foundry.api.app import app

    user = User(
        email="workflow@example.com",
        name="Workflow",
        password_hash=hash_password("securepass12"),
        is_admin=True,
    )
    session.add(user)
    session.commit()

    def override():
        yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        login = test_client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "securepass12"},
        )
        test_client.headers["Authorization"] = (
            f"Bearer {login.json()['access_token']}"
        )
        yield test_client
    app.dependency_overrides.clear()


def create_project(client):
    response = client.post(
        "/api/projects",
        json={
            "ref": "PR-900",
            "name": "Workflow pilot",
            "hypothesis": "A falsifiable claim",
            "customer": "Pilot customer",
            "form": "interactive",
            "stage": "idea",
            "visibility": "private",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_stage_is_gate_controlled(client):
    project = create_project(client)
    response = client.patch(
        f"/api/projects/{project['id']}", json={"stage": "prototype"}
    )
    assert response.status_code == 400


def test_capture_gate_creates_audited_first_experiment(client, session):
    project = create_project(client)
    blocked = client.post(
        f"/api/projects/{project['id']}/gate-reviews",
        json={"outcome": "advance", "rationale": "Ready"},
    )
    assert blocked.status_code == 409

    dossier = {
        "observable_problem": "Manual work obscures value",
        "expected_value": "Faster evidence",
        "falsification_condition": "No cycle-time reduction",
        "domain": "AI/ML",
        "initial_evidence": "Operator interviews",
        "minimum_testable_artifact": "Working workflow screen",
        "success_criteria": "One complete gate cycle",
    }
    assert (
        client.put(f"/api/projects/{project['id']}/dossier", json=dossier).status_code
        == 200
    )
    advanced = client.post(
        f"/api/projects/{project['id']}/gate-reviews",
        json={
            "outcome": "advance",
            "rationale": "Contract complete",
            "evidence_refs": ["interview:1"],
        },
    )
    assert advanced.status_code == 200, advanced.text
    assert session.get(Project, project["id"]).stage == "prototype"
    assert session.query(StageTransition).count() == 1
    assert session.query(AgentPrompt).count() == 1
    workflow = client.get(f"/api/projects/{project['id']}/workflow").json()
    assert len(workflow["experiments"]) == 1


def test_agent_prompt_claim_includes_repo_cwd_when_repos_root_set(client, tmp_path, monkeypatch):
    from foundry.config import settings

    repo = tmp_path / "waypoint"
    repo.mkdir()
    monkeypatch.setattr(settings, "repos_root", str(tmp_path))

    project = create_project(client)
    client.patch(f"/api/projects/{project['id']}", json={"repo_slug": "waypoint"})
    task = client.post(
        f"/api/projects/{project['id']}/tasks", json={"title": "Execute"}
    ).json()
    client.post(
        "/api/agent-prompts",
        json={"task_id": task["id"], "title": "Run", "prompt_text": "Do work"},
    )
    claim = client.post(
        "/api/agent-prompts/claim",
        json={"worker_id": "worker-cwd", "lease_seconds": 120},
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["repo_slug"] == "waypoint"
    assert body["repo_cwd"] == str(repo.resolve())


def test_agent_prompt_claim_emits_repo_cwd_hint_without_local_checkout(client, tmp_path, monkeypatch):
    """VPS may set FOUNDRY_REPOS_ROOT to a WSL path that does not exist on the API host."""
    from foundry.config import settings

    root = tmp_path / "missing-repos"
    monkeypatch.setattr(settings, "repos_root", str(root))

    project = create_project(client)
    client.patch(f"/api/projects/{project['id']}", json={"repo_slug": "waypoint"})
    task = client.post(
        f"/api/projects/{project['id']}/tasks", json={"title": "Execute"}
    ).json()
    client.post(
        "/api/agent-prompts",
        json={"task_id": task["id"], "title": "Run", "prompt_text": "Do work"},
    )
    claim = client.post(
        "/api/agent-prompts/claim",
        json={"worker_id": "worker-hint", "lease_seconds": 120},
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["repo_slug"] == "waypoint"
    assert body["repo_cwd"] == str(root / "waypoint")


def test_agent_prompt_claim_and_completion_are_idempotent(client):
    project = create_project(client)
    client.patch(
        f"/api/projects/{project['id']}",
        json={"repo_slug": "waypoint"},
    )
    task = client.post(
        f"/api/projects/{project['id']}/tasks", json={"title": "Execute"}
    ).json()
    prompt = client.post(
        "/api/agent-prompts",
        json={"task_id": task["id"], "title": "Run", "prompt_text": "Do work"},
    ).json()
    claim = client.post(
        "/api/agent-prompts/claim",
        json={"worker_id": "worker-1", "lease_seconds": 120},
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["repo_slug"] == "waypoint"
    assert body["project_ref"] == "PR-900"
    assert "repo_cwd" in body
    lease = body["lease_token"]
    payload = {
        "worker_id": "worker-1",
        "lease_token": lease,
        "success": True,
        "result": {"ok": True},
        "artifact_refs": ["git:abc123"],
    }
    url = f"/api/agent-prompts/{prompt['id']}/complete"
    first = client.post(url, json=payload)
    second = client.post(url, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["artifact_refs"] == ["git:abc123"]


@pytest.mark.parametrize(
    ("ref", "form"),
    [("PR-002", "interactive"), ("PR-004", "static")],
)
def test_two_form_pilot_reaches_release_gate(client, session, ref, form):
    project = client.post(
        "/api/projects",
        json={
            "ref": ref,
            "name": f"{form.title()} pilot",
            "hypothesis": "The artifact produces measurable value",
            "customer": "Pilot reviewer",
            "form": form,
            "stage": "idea",
            "visibility": "private",
        },
    ).json()
    dossier = {
        "observable_problem": "Current workflow is manual",
        "expected_value": "Shorter time to signal",
        "falsification_condition": "No measurable improvement",
        "domain": "AI/ML" if form == "interactive" else "Leadership",
        "initial_evidence": "Pilot request",
        "minimum_testable_artifact": "Testable pilot artifact",
        "success_criteria": "Two reviewers score the artifact",
    }
    client.put(f"/api/projects/{project['id']}/dossier", json=dossier)
    assert (
        client.post(
            f"/api/projects/{project['id']}/gate-reviews",
            json={"outcome": "advance", "rationale": "Capture complete"},
        ).status_code
        == 200
    )
    workflow = client.get(f"/api/projects/{project['id']}/workflow").json()
    experiment = workflow["experiments"][0]
    client.patch(
        f"/api/experiments/{experiment['id']}",
        json={"status": "running"},
    )
    artifact = client.post(
        f"/api/projects/{project['id']}/artifacts",
        json={
            "experiment_id": experiment["id"],
            "kind": "application" if form == "interactive" else "document",
            "title": "Pilot artifact",
            "uri": f"artifact:{ref}:v1",
            "version": "v1",
            "checks_status": "passed",
            "immutable": True,
        },
    ).json()
    assert (
        client.post(
            f"/api/projects/{project['id']}/gate-reviews",
            json={
                "outcome": "advance",
                "rationale": "Prototype is testable",
                "evidence_refs": [artifact["uri"]],
            },
        ).status_code
        == 200
    )
    link = EvaluationCampaignLink(
        project_id=project["id"],
        eval_campaign_id=1000 + project["id"],
        name="Pilot evaluation",
        status="completed",
        decision_status="approved",
        recommendation="advance",
        packet_json=json.dumps(
            {
                "confidence": "sufficient",
                "evidence_refs": [artifact["uri"]],
                "recommendation": "advance",
                "quantitative_results": {
                    "dimensions": {"usage": {"mean": 4.0}}
                },
            }
        ),
    )
    session.add(link)
    session.commit()
    assert (
        client.post(
            f"/api/projects/{project['id']}/gate-reviews",
            json={
                "outcome": "advance",
                "rationale": "Evidence supports release",
                "evidence_refs": ["eval:pilot"],
            },
        ).status_code
        == 200
    )
    release = client.post(
        f"/api/projects/{project['id']}/releases",
        json={
            "artifact_id": artifact["id"],
            "version": "v1",
            "target": f"https://example.test/{ref.lower()}",
            "rollback_reference": "artifact:previous",
            "monitoring_metric": "pilot_success_rate",
            "checks": {
                "security": True,
                "privacy": True,
                "licensing": True,
                "accessibility": True,
                "customer_acceptance": True,
                "backup_rollback": True,
                "monitoring": True,
            },
        },
    )
    assert release.status_code == 200, release.text
    assert release.json()["status"] == "approved"
