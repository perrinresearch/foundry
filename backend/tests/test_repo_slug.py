import pytest
from pydantic import ValidationError

from foundry.schemas import ProjectCreate, ProjectUpdate, normalize_repo_slug


@pytest.mark.parametrize(
    "slug",
    [
        "perrinresearch.com",
        "restore79",
        "my_project",
        "org.repo-name_1",
        "A",
        "x" * 100,
    ],
)
def test_normalize_repo_slug_allows_github_names(slug):
    assert normalize_repo_slug(slug) == slug


@pytest.mark.parametrize(
    "slug",
    [
        "-leading-hyphen",
        "ends.git",
        "Ends.GIT",
        ".",
        "..",
    ],
)
def test_normalize_repo_slug_rejects_invalid_names(slug):
    with pytest.raises(ValueError):
        normalize_repo_slug(slug)


def test_project_create_accepts_period_in_repo_slug():
    project = ProjectCreate(ref="PR-000", name="Site", repo_slug="perrinresearch.com")
    assert project.repo_slug == "perrinresearch.com"


def test_project_update_rejects_disallowed_characters():
    with pytest.raises(ValidationError):
        ProjectUpdate(repo_slug="bad/name")
