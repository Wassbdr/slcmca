"""Machine-readable check reports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import quote


class OutputFormat(str, Enum):
    text = "text"
    json = "json"
    sarif = "sarif"


@dataclass(frozen=True)
class Finding:
    rule: str
    message: str


def sarif_report(source: Path, findings: list[Finding]) -> dict:
    """Encode feasibility faults as SARIF 2.1.0 results."""
    path = source.resolve()
    try:
        uri = quote(path.relative_to(Path.cwd()).as_posix())
    except ValueError:
        uri = path.as_uri()
    rules = list(dict.fromkeys(finding.rule for finding in findings))
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "slacheck",
                "rules": [{"id": rule} for rule in rules],
            }},
            "results": [{
                "ruleId": finding.rule,
                "ruleIndex": rules.index(finding.rule),
                "level": "error",
                "message": {"text": finding.message},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": 1},
                }}],
            } for finding in findings],
        }],
    }
