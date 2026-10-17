from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from foundry.github_client import GitHubClient, GitHubClientError
from foundry.schemas import GitHubForkRequest


def _response(status_code: int, payload=None, headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload if payload is not None else {}
    resp.text = str(payload)
    resp.headers = headers or {}
    return resp


@pytest.fixture()
def client():
    with patch("foundry.github_client.settings") as settings:
        settings.github_token = "test-token"
        settings.github_org = "perrinresearch"
        with patch("foundry.github_client.httpx.Client") as client_cls:
            http = MagicMock()
            client_cls.return_value = http
            gh = GitHubClient()
            gh._owner_kind = "user"
            yield gh, http
            gh.close()


def test_list_repositories_filters_to_owner(client):
    gh, http = client
    http.get.return_value = _response(
        200,
        [
            {
                "name": "alpha",
                "private": True,
                "html_url": "https://github.com/perrinresearch/alpha",
                "default_branch": "main",
                "updated_at": "2026-01-01T00:00:00Z",
                "owner": {"login": "perrinresearch"},
            },
            {
                "name": "other",
                "private": False,
                "html_url": "https://github.com/someone/other",
                "default_branch": "main",
                "updated_at": "2026-01-02T00:00:00Z",
                "owner": {"login": "someone"},
            },
        ],
    )
    rows = gh.list_repositories()
    assert [row["name"] for row in rows] == ["alpha"]
    http.get.assert_called()
    assert http.get.call_args.args[0] == "/user/repos"


def test_get_repository_missing(client):
    gh, http = client
    http.get.return_value = _response(404, {"message": "Not Found"})
    assert gh.get_repository("missing") is None


def test_resolve_owner_kind_auth_failure():
    with patch("foundry.github_client.settings") as settings:
        settings.github_token = "bad-token"
        settings.github_org = "perrinresearch"
        with patch("foundry.github_client.httpx.Client") as client_cls:
            http = MagicMock()
            client_cls.return_value = http
            gh = GitHubClient()
            http.get.side_effect = [
                _response(401, {"message": "Bad credentials"}),
                _response(401, {"message": "Bad credentials"}),
            ]
            with pytest.raises(GitHubClientError, match="authentication failed"):
                gh._resolve_owner_kind()
            gh.close()


def test_fork_repository_polls_until_ready(client):
    gh, http = client
    http.post.return_value = _response(
        202,
        {
            "name": "Hello-World",
            "html_url": "https://github.com/perrinresearch/Hello-World",
            "default_branch": "main",
        },
    )
    http.get.side_effect = [
        _response(404, {"message": "Not Found"}),
        _response(
            200,
            {
                "name": "Hello-World",
                "html_url": "https://github.com/perrinresearch/Hello-World",
                "default_branch": "main",
                "private": True,
            },
        ),
    ]
    remote = gh.fork_repository(
        "octocat",
        "Hello-World",
        poll_attempts=3,
        poll_interval_seconds=0,
    )
    assert remote["name"] == "Hello-World"
    http.post.assert_called_once()
    assert http.post.call_args.args[0] == "/repos/octocat/Hello-World/forks"


def test_fork_repository_org_sets_organization():
    with patch("foundry.github_client.settings") as settings:
        settings.github_token = "test-token"
        settings.github_org = "perrinresearch"
        with patch("foundry.github_client.httpx.Client") as client_cls:
            http = MagicMock()
            client_cls.return_value = http
            gh = GitHubClient()
            gh._owner_kind = "org"
            http.post.return_value = _response(
                202, {"name": "Hello-World", "html_url": "https://example/x"}
            )
            http.get.return_value = _response(
                200,
                {
                    "name": "Hello-World",
                    "html_url": "https://github.com/perrinresearch/Hello-World",
                    "default_branch": "main",
                },
            )
            gh.fork_repository("octocat", "Hello-World", poll_interval_seconds=0)
            assert http.post.call_args.kwargs["json"]["organization"] == "perrinresearch"
            gh.close()


def test_ensure_repository_returns_existing(client):
    gh, http = client
    http.get.return_value = _response(
        200,
        {
            "name": "waypoint",
            "html_url": "https://github.com/perrinresearch/waypoint",
            "default_branch": "main",
        },
    )
    remote = gh.ensure_repository("waypoint")
    assert remote["name"] == "waypoint"
    http.post.assert_not_called()


def test_fork_request_schema():
    body = GitHubForkRequest(source="octocat/Hello-World", name="hello")
    assert body.source == "octocat/Hello-World"
    assert body.name == "hello"
    with pytest.raises(ValidationError):
        GitHubForkRequest(source="not-a-pair")
