"""Write a synthetic trace using the public Jaeger HotROD service layout."""

from __future__ import annotations

import json
from pathlib import Path

SERVICES = [
    ("frontend", None), ("customer", "frontend"), ("mysql", "customer"),
    ("driver", "frontend"), ("redis", "driver"), ("route", "frontend"),
]


def main() -> None:
    timestamp = 1_700_000_000_000_000_000
    span_ids = {name: f"{i:016x}" for i, (name, _) in enumerate(SERVICES, 1)}
    resources = []
    for i, (name, parent) in enumerate(SERVICES):
        span = {
            "name": name,
            "traceId": f"{1:032x}",
            "spanId": span_ids[name],
            "kind": 2,
            "startTimeUnixNano": str(timestamp + i * 1_000_000),
            "endTimeUnixNano": str(timestamp + (12 - i) * 1_000_000),
        }
        if parent:
            span["parentSpanId"] = span_ids[parent]
        resources.append({
            "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": name}}]},
            "scopeSpans": [{"scope": {"name": "hotrod-sample"}, "spans": [span]}],
        })
    output = Path(__file__).resolve().parents[1] / "examples" / "hotrod.otlp.json"
    output.write_text(json.dumps({"resourceSpans": resources}, indent=2) + "\n")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
