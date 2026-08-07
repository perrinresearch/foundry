from __future__ import annotations

from typing import Any, Literal

import httpx

from foundry.config import settings


class GitHubClientError(RuntimeError):
    pass


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
        raise GitHubClientError(
            f"FOUNDRY_GITHUB_ORG={self.owner!r} is neither a visible GitHub "
            f"organization nor user (org={org.status_code}, user={user.status_code})"
        )

    def ensure_repository(
        self, slug: str, *, description: str = "", private: bool = True
    ) -> dict[str, Any]:
        response = self.client.get(f"/repos/{self.owner}/{slug}")
        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            raise GitHubClientError(
                f"GitHub repository lookup failed: {response.status_code} {response.text}"
            )
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
