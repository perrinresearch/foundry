from __future__ import annotations

from typing import Any

import httpx

from foundry.config import settings


class EvalClientError(RuntimeError):
    pass


class EvalClient:
    def __init__(self) -> None:
        self.base_url = settings.eval_api_url.rstrip("/")
        self.client = httpx.Client(timeout=60)
        self.token = ""

    def close(self) -> None:
        self.client.close()

    def _headers(self) -> dict[str, str]:
        if not self.token:
            response = self.client.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "email": settings.eval_email,
                    "password": settings.eval_password,
                },
            )
            if response.status_code >= 400:
                raise EvalClientError(
                    f"Eval login failed: {response.status_code} {response.text}"
                )
            self.token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self.token}"}

    def create_campaign(self, project_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/api/projects/{project_ref}/campaigns",
            headers=self._headers(),
            json=payload,
        )
        if response.status_code >= 400:
            raise EvalClientError(
                f"Create Eval campaign failed: {response.status_code} {response.text}"
            )
        return response.json()

    def decision_packet(self, project_ref: str, campaign_id: int) -> dict[str, Any]:
        response = self.client.get(
            f"{self.base_url}/api/projects/{project_ref}/campaigns/"
            f"{campaign_id}/decision-packet",
            headers=self._headers(),
        )
        if response.status_code >= 400:
            raise EvalClientError(
                f"Eval decision packet failed: {response.status_code} {response.text}"
            )
        return response.json()

    def record_decision(
        self, project_ref: str, campaign_id: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = self.client.post(
            f"{self.base_url}/api/projects/{project_ref}/campaigns/"
            f"{campaign_id}/decision",
            headers=self._headers(),
            json=payload,
        )
        if response.status_code >= 400:
            raise EvalClientError(
                f"Eval decision reconciliation failed: "
                f"{response.status_code} {response.text}"
            )
        return response.json()
