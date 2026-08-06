from foundry.forms import (
    capture_agent_prompt_text,
    default_artifact_kind,
    kind_for_form,
    normalize_form,
    required_release_checks,
)


def test_normalize_and_portfolio_kind():
    assert normalize_form("physical") == "physical"
    assert normalize_form("unknown") == "interactive"
    assert kind_for_form("physical") == "product"
    assert kind_for_form("static") == "blog"
    assert kind_for_form("interactive") == "application"


def test_release_checks_are_form_aware():
    assert "cost_justification" in required_release_checks("physical")
    assert "security" not in required_release_checks("physical")
    assert "security" in required_release_checks("interactive")
    assert "licensing" in required_release_checks("static")
    assert "accessibility" in required_release_checks("static")


def test_physical_capture_prompt():
    text = capture_agent_prompt_text(
        ref="PR-007",
        name="Demo",
        hypothesis="Users want X",
        acceptance_criteria="Survey support",
        form="physical",
        minimum_testable_artifact="Diagram + rendering",
    )
    assert "Form: physical" in text
    assert "mockup package" in text
    assert default_artifact_kind("physical") == "mockup"
