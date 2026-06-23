"""Shared test fixtures: paths to bundled fixtures and the paper's scenario as objects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from slacheck.models import Component, SloValues

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures"
DD_FIXTURES = FIXTURES / "datadog"


@pytest.fixture
def fixtures_dir() -> Path:
    return DD_FIXTURES


def _load_dd(name: str) -> dict:
    return json.loads((DD_FIXTURES / name).read_text())


@pytest.fixture
def dd_fixture():
    """Load a raw Datadog fixture JSON by file name."""
    return _load_dd


@pytest.fixture
def paper_scenario() -> dict:
    """The paper's example as {'global_target': SloValues, 'components': [Component]}."""
    raw = yaml.safe_load((FIXTURES / "scenarios" / "paper_example.yaml").read_text())
    return {
        "global_target": SloValues(**raw["global_target"]),
        "components": [
            Component(name=c["name"], csp=c.get("csp"), slo=SloValues(**c["slo"]))
            for c in raw["components"]
        ],
    }
