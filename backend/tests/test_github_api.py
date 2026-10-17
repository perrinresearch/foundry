from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from foundry.auth import hash_password
from foundry.database import Base, get_db
from foundry.models import User


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
        email="github@example.com",
        name="GitHub",
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


def test_list_github_repos(client):
    mock_client = MagicMock()
    mock_client.list_repositories.return_value = [
        {
            "name": "waypoint",
            "private": True,
            "html_url": "https://github.com/perrinresearch/waypoint",
            "default_branch": "main",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]
    with patch("foundry.api.app.GitHubClient", return_value=mock_client):
        response = client.get("/api/github/repos")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body[0]["name"] == "waypoint"
    mock_client.close.assert_called_once()


def test_fork_github_repository(client):
    mock_client = MagicMock()
    mock_client.fork_repository.return_value = {
        "name": "hello-fork",
        "html_url": "https://github.com/perrinresearch/hello-fork",
        "default_branch": "main",
    }
    with patch("foundry.api.app.GitHubClient", return_value=mock_client):
        response = client.post(
            "/api/github/forks",
            json={"source": "octocat/Hello-World", "name": "hello-fork"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repo_slug"] == "hello-fork"
    assert body["html_url"].endswith("/hello-fork")
    mock_client.fork_repository.assert_called_once_with(
        "octocat", "Hello-World", name="hello-fork"
    )


def test_create_project_with_existing_repo_slug(client):
    response = client.post(
        "/api/projects",
        json={
            "ref": "PR-910",
            "name": "Existing repo project",
            "hypothesis": "Link works",
            "repo_slug": "waypoint",
            "stage": "idea",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["repo_slug"] == "waypoint"
