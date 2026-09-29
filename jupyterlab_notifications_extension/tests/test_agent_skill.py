"""The agent skill installed by the wheel is the one in the repository.

The skill ships twice: the repository copy an agent reads from a clone, and the
copy the wheel's shared-data mapping puts under `sys.prefix`. Two copies drift,
so they are compared byte for byte here. This fails when the mapping is absent
from `pyproject.toml`, when the installed copy is older than the repository
copy, and when the skill is renamed on one side only.
"""
import pathlib
import sys

import pytest

SKILL_NAME = "jupyterlab-notifications-extension"

_REPOSITORY_COPY = (
    pathlib.Path(__file__).resolve().parents[2]
    / ".agents" / "skills" / SKILL_NAME / "SKILL.md"
)

_INSTALLED_COPY = (
    pathlib.Path(sys.prefix)
    / "share" / "jupyter" / "agents" / "skills" / SKILL_NAME / "SKILL.md"
)


@pytest.mark.skipif(
    not _REPOSITORY_COPY.is_file(),
    reason="no repository copy to compare against outside a source checkout",
)
def test_installed_agent_skill_matches_repository():
    assert _INSTALLED_COPY.is_file(), (
        f"{_INSTALLED_COPY} is missing: the installed wheel carries no agent "
        "skill, so either the shared-data mapping is absent from pyproject.toml "
        "or this environment predates it - run make install"
    )
    assert _INSTALLED_COPY.read_bytes() == _REPOSITORY_COPY.read_bytes(), (
        "the installed agent skill differs from the repository copy; the "
        "wheel in this environment was built from an older SKILL.md"
    )
