"""Sync Foundry project pipeline data into the public site portfolio source."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from foundry.config import settings
from foundry.models import PROJECT_STAGES, Project


@dataclass
class PortfolioSyncResult:
    success: bool
    message: str
    updated_refs: list[str]


def _escape_ts_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _find_prototype_block(content: str, ref: str) -> tuple[int, int] | None:
    marker = f'ref: "{ref}"'
    idx = content.find(marker)
    if idx == -1:
        return None
    start = content.rfind("{", 0, idx)
    end = content.find("  },", idx)
    if end == -1:
        end = content.find("\n  }", idx)
    if end == -1 or start == -1:
        return None
    if content[end : end + 3] == "  },":
        end += 4
    else:
        end += len("\n  }")
    return start, end


def _replace_quoted_field(block: str, field: str, value: str) -> str:
    escaped = _escape_ts_string(value)
    pattern = rf'({re.escape(field)}:\s*")([^"]*)(")'
    if not re.search(pattern, block):
        return block
    return re.sub(pattern, rf"\1{escaped}\3", block, count=1)


def _replace_hypothesis_field(block: str, value: str) -> str:
    escaped = _escape_ts_string(value)
    multiline = r'(hypothesis:\s*\n\s*")([^"]*)(")'
    if re.search(multiline, block):
        return re.sub(multiline, rf"\1{escaped}\3", block, count=1)
    return _replace_quoted_field(block, "hypothesis", value)


def sync_portfolio_from_db(db: Session, portfolio_path: Path | None = None) -> PortfolioSyncResult:
    path = portfolio_path or settings.site_portfolio_file
    if not path.is_file():
        return PortfolioSyncResult(
            success=False,
            message=f"Portfolio file not found: {path}",
            updated_refs=[],
        )

    content = path.read_text(encoding="utf-8")
    projects = (
        db.query(Project)
        .filter(Project.status == "active")
        .order_by(Project.ref)
        .all()
    )
    replacements: list[tuple[int, int, str]] = []
    updated_refs: list[str] = []

    for project in projects:
        if project.stage not in PROJECT_STAGES:
            continue
        span = _find_prototype_block(content, project.ref)
        if span is None:
            continue
        start, end = span
        block = content[start:end]
        new_block = block
        new_block = _replace_quoted_field(new_block, "stage", project.stage)
        new_block = _replace_quoted_field(new_block, "name", project.name)
        new_block = _replace_hypothesis_field(new_block, project.hypothesis)
        new_block = _replace_quoted_field(new_block, "form", project.form)
        if new_block != block:
            replacements.append((start, end, new_block))
            updated_refs.append(project.ref)

    for start, end, new_block in sorted(replacements, key=lambda item: item[0], reverse=True):
        content = content[:start] + new_block + content[end:]

    if replacements:
        path.write_text(content, encoding="utf-8")

    message = (
        f"Updated portfolio for {', '.join(updated_refs)}."
        if updated_refs
        else "No matching portfolio entries to update."
    )
    return PortfolioSyncResult(success=True, message=message, updated_refs=updated_refs)
