"""Build and publish the public Astro site to dev.perrinresearch.com/public."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from foundry.config import settings
from foundry.deploy.portfolio import sync_portfolio_from_db
from foundry.schemas import SiteDeployOut

SITE_PROJECT_REF = "PR-000"


class SiteDeployError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        detail: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.detail = detail


@dataclass
class DeployResult:
    success: bool
    message: str
    stdout: str
    stderr: str
    exit_code: int
    target_url: str
    public_dir: str


def deploy_public_site() -> DeployResult:
    script = settings.site_deploy_script
    if not script.is_file():
        return DeployResult(
            success=False,
            message=f"Deploy script not found: {script}",
            stdout="",
            stderr="",
            exit_code=1,
            target_url=settings.site_public_url,
            public_dir=str(settings.site_public_dir),
        )

    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        timeout=settings.site_deploy_timeout_seconds,
        cwd=str(script.parent),
    )
    ok = proc.returncode == 0
    message = "Site deployed successfully." if ok else "Site deploy failed."
    return DeployResult(
        success=ok,
        message=message,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        target_url=settings.site_public_url,
        public_dir=str(settings.site_public_dir),
    )


def project_supports_site_deploy(ref: str) -> bool:
    return ref == SITE_PROJECT_REF


def run_site_deploy(db: Session) -> SiteDeployOut:
    """Sync active portfolio projects and publish the public site."""
    sync = sync_portfolio_from_db(db)
    if not sync.success:
        raise SiteDeployError(400, sync.message)
    result = deploy_public_site()
    if not result.success:
        raise SiteDeployError(
            502,
            result.message,
            detail={
                "message": result.message,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "target_url": result.target_url,
                "public_dir": result.public_dir,
                "synced_refs": sync.updated_refs,
            },
        )
    deploy_message = result.message
    if sync.updated_refs:
        deploy_message = f"{sync.message} {deploy_message}"
    return SiteDeployOut(
        success=result.success,
        message=deploy_message,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        target_url=result.target_url,
        public_dir=result.public_dir,
        synced_refs=sync.updated_refs,
    )
