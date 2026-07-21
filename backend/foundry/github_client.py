from __future__ import annotations

from typing import Any

import httpx

from foundry.config import settings


class GitHubClientError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self) -> None:
        if not settings.github_token:
            raise GitHubClientError("FOUNDRY_GITHUB_TOKEN is not configured")
        self.client = httpx.Client(
            base_url="https://api.github.com",
            timeout=60,
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    def close(self) -> None:
        self.client.close()

    def ensure_repository(
        self, slug: str, *, description: str = "", private: bool = True
    ) -> dict[str, Any]:
        response = self.client.get(f"/repos/{settings.github_org}/{slug}")
        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            raise GitHubClientError(
                f"GitHub repository lookup failed: {response.status_code} {response.text}"
            )
        response = self.client.post(
            f"/orgs/{settings.github_org}/repos",
            json={
                "name": slug,
                "description": description,
                "private": private,
                "auto_init": True,
            },
        )
        if response.status_code >= 400:
            raise GitHubClientError(
                f"GitHub repository creation failed: {response.status_code} {response.text}"
            )
        return response.json()
