from __future__ import annotations

import time
from typing import Any, Literal

import httpx

from foundry.config import settings


class GitHubClientError(RuntimeError):
    pass


def _repo_summary(remote: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": str(remote.get("name") or ""),
        "private": bool(remote.get("private")),
        "html_url": str(remote.get("html_url") or ""),
        "default_branch": str(remote.get("default_branch") or "main"),
        "updated_at": str(remote.get("updated_at") or ""),
    }


class GitHubClient:
    def __init__(self) -> None:
        if not settings.github_token:
            raise GitHubClientError("FOUNDRY_GITHUB_TOKEN is not configured")
        self.owner = (settings.github_org or "").strip()
        if not self.owner:
            raise GitHubClientError("FOUNDRY_GITHUB_ORG is not configured")
        self.client = httpx.Client(
            base_url="https://api.github.com",
            timeout=60,
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        self._owner_kind: Literal["org", "user"] | None = None

    def close(self) -> None:
        self.client.close()

    def _resolve_owner_kind(self) -> Literal["org", "user"]:
        if self._owner_kind is not None:
            return self._owner_kind
        org = self.client.get(f"/orgs/{self.owner}")
        if org.status_code == 200:
            self._owner_kind = "org"
            return self._owner_kind
        user = self.client.get(f"/users/{self.owner}")
        if user.status_code == 200:
            self._owner_kind = "user"
            return self._owner_kind
        if org.status_code in (401, 403) or user.status_code in (401, 403):
            raise GitHubClientError(
                "GitHub authentication failed (check FOUNDRY_GITHUB_TOKEN). "
                f"org={org.status_code} user={user.status_code}"
            )
        raise GitHubClientError(
            f"FOUNDRY_GITHUB_ORG={self.owner!r} is neither a visible GitHub "
            f"organization nor user (org={org.status_code}, user={user.status_code})"
        )

    def _paginate(self, path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        query = {"per_page": 100, **(params or {})}
        page = 1
        while True:
            response = self.client.get(path, params={**query, "page": page})
            if response.status_code >= 400:
                raise GitHubClientError(
                    f"GitHub list failed: {response.status_code} {response.text}"
                )
            batch = response.json()
            if not isinstance(batch, list):
                raise GitHubClientError(f"GitHub list returned unexpected payload for {path}")
            items.extend(batch)
            link = response.headers.get("link", "")
            if 'rel="next"' not in link:
                break
            page += 1
            if page > 50:
                break
        return items

    def list_repositories(self) -> list[dict[str, Any]]:
        kind = self._resolve_owner_kind()
        if kind == "org":
            remotes = self._paginate(f"/orgs/{self.owner}/repos", params={"type": "all"})
        else:
            remotes = self._paginate(
                "/user/repos",
                params={"affiliation": "owner", "sort": "updated"},
            )
            remotes = [
                row
                for row in remotes
                if str((row.get("owner") or {}).get("login") or "").lower()
                == self.owner.lower()
            ]
        summaries = [_repo_summary(row) for row in remotes if row.get("name")]
        summaries.sort(key=lambda row: row["name"].lower())
        return summaries

    def get_repository(self, slug: str) -> dict[str, Any] | None:
        response = self.client.get(f"/repos/{self.owner}/{slug}")
        if response.status_code == 200:
            return response.json()
        if response.status_code == 404:
            return None
        raise GitHubClientError(
            f"GitHub repository lookup failed: {response.status_code} {response.text}"
        )

    def fork_repository(
        self,
        source_owner: str,
        source_repo: str,
        *,
        name: str | None = None,
        poll_attempts: int = 20,
        poll_interval_seconds: float = 1.0,
    ) -> dict[str, Any]:
        source_owner = source_owner.strip()
        source_repo = source_repo.strip()
        if not source_owner or not source_repo:
            raise GitHubClientError("Fork source must be owner/repo")
        payload: dict[str, Any] = {}
        if name and name.strip():
            payload["name"] = name.strip()
        kind = self._resolve_owner_kind()
        if kind == "org":
            payload["organization"] = self.owner
        response = self.client.post(
            f"/repos/{source_owner}/{source_repo}/forks",
            json=payload or None,
        )
        if response.status_code >= 400:
            raise GitHubClientError(
                f"GitHub fork failed: {response.status_code} {response.text}"
            )
        remote = response.json()
        expected_name = (name or source_repo).strip() or source_repo
        # GitHub often returns 202 and finishes the fork asynchronously.
        for _ in range(max(1, poll_attempts)):
            ready = self.get_repository(str(remote.get("name") or expected_name))
            if ready is not None:
                return ready
            time.sleep(poll_interval_seconds)
        raise GitHubClientError(
            f"Timed out waiting for fork {self.owner}/{expected_name} to become ready"
        )

    def ensure_repository(
        self, slug: str, *, description: str = "", private: bool = True
    ) -> dict[str, Any]:
        existing = self.get_repository(slug)
        if existing is not None:
            return existing
        payload = {
            "name": slug,
            "description": description,
            "private": private,
            "auto_init": True,
        }
        kind = self._resolve_owner_kind()
        if kind == "org":
            response = self.client.post(f"/orgs/{self.owner}/repos", json=payload)
        else:
            # Personal account: create under the authenticated user.
            response = self.client.post("/user/repos", json=payload)
        if response.status_code >= 400:
            raise GitHubClientError(
                f"GitHub repository creation failed: {response.status_code} {response.text}"
            )
        return response.json()
