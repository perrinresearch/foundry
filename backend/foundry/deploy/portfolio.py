"""Sync Foundry project pipeline data into the public site portfolio source."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from foundry.config import settings
from foundry.forms import kind_for_form, normalize_form
from foundry.models import PROJECT_STAGES, Project


@dataclass
class PortfolioSyncResult:
    success: bool
    message: str
    updated_refs: list[str] = field(default_factory=list)
    added_refs: list[str] = field(default_factory=list)
    removed_refs: list[str] = field(default_factory=list)


def _escape_ts_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _slugify(name: str, ref: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or ref.lower().replace("_", "-")


def _kind_for_form(form: str) -> str:
    return kind_for_form(form)


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
    # Include trailing newline after the block when present
    if end < len(content) and content[end] == "\n":
        end += 1
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


def _format_prototype_block(project: Project) -> str:
    name = _escape_ts_string(project.name)
    hyp = _escape_ts_string(project.hypothesis or "")
    form = normalize_form(project.form)
    stage = project.stage if project.stage in PROJECT_STAGES else "idea"
    kind = _kind_for_form(form)
    slug = _slugify(project.name, project.ref)
    return (
        f"  {{\n"
        f'    id: "{slug}",\n'
        f'    ref: "{project.ref}",\n'
        f'    name: "{name}",\n'
        f"    hypothesis:\n"
        f'      "{hyp}",\n'
        f'    form: "{form}",\n'
        f'    kind: "{kind}",\n'
        f'    stage: "{stage}",\n'
        f"  }},\n"
    )


def _prototypes_array_end(content: str) -> int | None:
    marker = "export const prototypes: Prototype[] = ["
    start = content.find(marker)
    if start == -1:
        return None
    # Find the matching closing ]; after the array start (first ]; that follows)
    close = content.find("\n];", start)
    return close if close != -1 else None


def _should_publish(project: Project) -> bool:
    visibility = getattr(project, "visibility", None) or "public"
    return (
        project.status == "active"
        and visibility == "public"
        and project.stage == "shipped"
        and any(release.status in ("approved", "released") for release in project.releases)
    )


def sync_portfolio_from_db(db: Session, portfolio_path: Path | None = None) -> PortfolioSyncResult:
    path = portfolio_path or settings.site_portfolio_file
    if not path.is_file():
        return PortfolioSyncResult(
            success=False,
            message=f"Portfolio file not found: {path}",
        )

    content = path.read_text(encoding="utf-8")
    projects = db.query(Project).order_by(Project.ref).all()

    updated_refs: list[str] = []
    added_refs: list[str] = []
    removed_refs: list[str] = []
    replacements: list[tuple[int, int, str]] = []
    to_insert: list[Project] = []

    for project in projects:
        span = _find_prototype_block(content, project.ref)
        if _should_publish(project):
            if span is None:
                to_insert.append(project)
                continue
            start, end = span
            block = content[start:end]
            # Strip trailing newline for field replacement, restore after
            trailing_nl = block.endswith("\n")
            core = block[:-1] if trailing_nl else block
            new_core = core
            new_core = _replace_quoted_field(new_core, "stage", project.stage)
            new_core = _replace_quoted_field(new_core, "name", project.name)
            new_core = _replace_hypothesis_field(new_core, project.hypothesis)
            form = normalize_form(project.form)
            new_core = _replace_quoted_field(new_core, "form", form)
            kind = _kind_for_form(form)
            new_core = _replace_quoted_field(new_core, "kind", kind)
            new_block = new_core + ("\n" if trailing_nl else "")
            if new_block != block:
                replacements.append((start, end, new_block))
                updated_refs.append(project.ref)
        elif span is not None:
            replacements.append((span[0], span[1], ""))
            removed_refs.append(project.ref)

    for start, end, new_block in sorted(replacements, key=lambda item: item[0], reverse=True):
        content = content[:start] + new_block + content[end:]

    if to_insert:
        array_end = _prototypes_array_end(content)
        if array_end is None:
            return PortfolioSyncResult(
                success=False,
                message="Could not locate prototypes array in portfolio.ts",
                updated_refs=updated_refs,
                added_refs=[],
                removed_refs=removed_refs,
            )
        blocks = "".join(_format_prototype_block(p) for p in to_insert)
        content = content[:array_end] + "\n" + blocks + content[array_end:]
        added_refs = [p.ref for p in to_insert]

    if replacements or to_insert:
        path.write_text(content, encoding="utf-8")

    parts: list[str] = []
    if updated_refs:
        parts.append(f"Updated {', '.join(updated_refs)}")
    if added_refs:
        parts.append(f"Added {', '.join(added_refs)}")
    if removed_refs:
        parts.append(f"Removed {', '.join(removed_refs)}")
    message = ". ".join(parts) + "." if parts else "No portfolio changes."

    return PortfolioSyncResult(
        success=True,
        message=message,
        updated_refs=updated_refs + added_refs,
        added_refs=added_refs,
        removed_refs=removed_refs,
    )
