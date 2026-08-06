"""Output forms and form-aware operating-model helpers."""

from __future__ import annotations

PROJECT_FORMS = ("interactive", "static", "physical")

FORM_PORTFOLIO_KIND = {
    "interactive": "application",
    "static": "blog",
    "physical": "product",
}

INTERACTIVE_RELEASE_CHECKS = (
    "security",
    "privacy",
    "licensing",
    "accessibility",
    "customer_acceptance",
    "backup_rollback",
    "monitoring",
)

STATIC_RELEASE_CHECKS = (
    "licensing",
    "accessibility",
    "customer_acceptance",
    "backup_rollback",
    "monitoring",
)

PHYSICAL_RELEASE_CHECKS = (
    "safety",
    "cost_justification",
    "manufacturability",
    "regulatory",
    "customer_acceptance",
    "backup_rollback",
    "monitoring",
)

PHYSICAL_ARTIFACT_KINDS = (
    "design_diagram",
    "rendering",
    "mockup",
    "model_3d",
    "prototype_photo",
    "bom",
    "cost_estimate",
    "document",
    "other",
)


def normalize_form(form: str | None) -> str:
    value = (form or "").strip().lower()
    if value in PROJECT_FORMS:
        return value
    return "interactive"


def kind_for_form(form: str | None) -> str:
    return FORM_PORTFOLIO_KIND[normalize_form(form)]


def required_release_checks(form: str | None) -> tuple[str, ...]:
    normalized = normalize_form(form)
    if normalized == "physical":
        return PHYSICAL_RELEASE_CHECKS
    if normalized == "static":
        return STATIC_RELEASE_CHECKS
    return INTERACTIVE_RELEASE_CHECKS


def default_artifact_kind(form: str | None) -> str:
    normalized = normalize_form(form)
    if normalized == "physical":
        return "mockup"
    if normalized == "static":
        return "document"
    return "application"


def capture_agent_prompt_text(
    *,
    ref: str,
    name: str,
    hypothesis: str,
    acceptance_criteria: str,
    form: str | None,
    minimum_testable_artifact: str = "",
) -> str:
    normalized = normalize_form(form)
    header = (
        f"Project: {ref} {name}\n"
        f"Form: {normalized}\n"
        f"Hypothesis: {hypothesis}\n"
        f"Acceptance criteria: {acceptance_criteria}\n"
    )
    if normalized == "physical":
        mta = minimum_testable_artifact or (
            "design diagrams, renderings/mockups, and stated value claims"
        )
        return (
            header
            + f"Minimum testable artifact: {mta}\n"
            "Create the smallest mockup package that can test this claim before a full build. "
            "Include 1–3 design diagrams or renderings, explicit value claims under test, "
            "and a rough build-cost band for the next fidelity step. "
            "Report immutable artifact references (diagram/rendering/mockup URIs) and checks."
        )
    if normalized == "static":
        return (
            header
            + "Create the smallest publication artifact that can test this claim. "
            "Report immutable artifact references and checks."
        )
    return (
        header
        + "Create the smallest artifact that can test this claim. "
        "Report immutable artifact references and checks."
    )
