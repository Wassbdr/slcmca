"""Shared test fixtures: paths to bundled fixtures and the paper's scenario as objects."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from slacheck.models import (
    Component,
    CspProfile,
    DependencyEdge,
    DependencyGraph,
    KnowledgeBase,
    ReconfigStrategy,
    SloValues,
)

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


def load_v2_scenario(path: Path) -> dict:
    """Parse a paper-v2 superset YAML into engine inputs.

    Returns {'graph': DependencyGraph, 'target': SloValues|None, 'kb': KnowledgeBase|None,
             'strategies': [ReconfigStrategy], 'target_slos': [str]}.
    """
    raw = yaml.safe_load(path.read_text())
    components = {
        c["name"]: Component(
            name=c["name"],
            csp=c.get("csp"),
            slo=SloValues(**c["slo"]),
            csp_profile=CspProfile(**c["csp_profile"]) if c.get("csp_profile") else None,
        )
        for c in raw["components"]
    }
    graph = DependencyGraph(
        components=components,
        edges=[DependencyEdge(**e) for e in raw.get("edges", [])],
        entrypoint=raw["entrypoint"],
    )
    target = SloValues(**raw["global_target"]) if raw.get("global_target") else None
    kb = KnowledgeBase(**raw["knowledge_base"]) if raw.get("knowledge_base") else None
    strategies = [ReconfigStrategy(**s) for s in raw.get("reconfig_strategies", [])]
    return {
        "graph": graph,
        "target": target,
        "kb": kb,
        "strategies": strategies,
        "target_slos": raw.get("target_slos", []),
    }


@pytest.fixture
def paper_scenario_v2() -> dict:
    return load_v2_scenario(FIXTURES / "scenarios" / "paper_example_v2.yaml")


@pytest.fixture
def paper_scenario_v2_redundant() -> dict:
    return load_v2_scenario(FIXTURES / "scenarios" / "paper_example_v2_redundant.yaml")
