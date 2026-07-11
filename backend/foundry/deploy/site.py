"""Build and publish the public Astro site to dev.perrinresearch.com/public."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from foundry.config import settings

SITE_PROJECT_REF = "PR-000"


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
