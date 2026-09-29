"""One claim, many documents: the test that fails when a sweep misses a site.

Three consecutive review rounds found a claim corrected in the code and left
standing in one document, because completeness was checked only by a grep
written in the same breath as the fix. Each row below is a wording that was
retired by a change to behaviour; the test fails for as long as any shipped
surface still carries it, so the sweep leaves an artifact rather than a memory.

Scope is the documentation that describes the tree as it stands: the README,
the CLI's own help, the frontend and the agent skill. It excludes
docs/defects.md and docs/acc-crit-*.md, whose closed entries quote
retired wording on purpose, and CHANGELOG.md, whose per-version sections are
a record of what each release contained and stay true after the thing named
in them is removed.
"""
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Every shipped surface that states behaviour in prose.
SURFACES = [
    "README.md",
    "jupyterlab_notifications_extension/cli.py",
    "jupyterlab_notifications_extension/routes.py",
    "src/index.ts",
    "src/request.ts",
    "src/utils.ts",
    ".agents/skills/jupyterlab-notifications-extension/SKILL.md",
]

# retired wording -> what replaced it, and why the old one is now false
RETIRED = {
    "may not be loopback": (
        "might not be loopback; 'may' reads as permission, and the sentence "
        "must also name the 0.0.0.0 -> 127.0.0.1 substitution"
    ),
    "is not loopback if": (
        "might not be loopback; false for --ip 127.0.0.1, localhost, ::1 "
        "and 0.0.0.0"
    ),
    "ALLOW_UNAUTHENTICATED_LOCALHOST": (
        "removed; the endpoints are authenticated on every host"
    ),
    "must cover 127.0.0.1 or [::1]": (
        "too narrow; an --ip-bound server is addressed at its own address, "
        "which the same epilog says twenty lines above"
    ),
    "whose host matches its certificate": (
        "a listed server is addressed at the loopback literal its record names, "
        "and an --ip-bound one at its own address"
    ),
    "requires an explicit --token": (
        "no target requires that flag; JUPYTERLAB_NOTIFY_TOKEN carries a "
        "credential to any target, and --token is the argv-exposing alternative"
    ),
}


@pytest.mark.parametrize("path", SURFACES)
def test_no_shipped_surface_carries_a_retired_claim(path):
    text = (_ROOT / path).read_text(encoding="utf-8")
    stale = {phrase: why for phrase, why in RETIRED.items() if phrase in text}
    assert not stale, f"{path} carries retired wording: {stale}"

