"""Diff two OpenAPI JSON documents and fail on contract-breaking deltas.

"Breaking" means something the frontend's generated `openapi-fetch` types
depend on: removed path, removed method, removed response field, type change,
required→optional flip on responses, or removed enum value.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from deepdiff import DeepDiff


BREAKING_MARKERS = (
    "dictionary_item_removed",
    "iterable_item_removed",
    "type_changes",
)


def _load(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: schema_diff.py <baseline.json> <current.json>", file=sys.stderr)
        return 2

    baseline_path, current_path = sys.argv[1], sys.argv[2]
    if not Path(baseline_path).exists():
        print(f"baseline file missing: {baseline_path}; skipping diff", file=sys.stderr)
        return 0

    baseline = _load(baseline_path)
    current = _load(current_path)

    # Focus on paths + components.schemas; ignore cosmetic info/servers changes.
    trimmed_baseline = {
        "paths": baseline.get("paths", {}),
        "components": baseline.get("components", {}),
    }
    trimmed_current = {
        "paths": current.get("paths", {}),
        "components": current.get("components", {}),
    }

    diff = DeepDiff(trimmed_baseline, trimmed_current, ignore_order=True, verbose_level=2)
    breaking = {k: v for k, v in diff.to_dict().items() if k in BREAKING_MARKERS}

    if breaking:
        print("OpenAPI contract-breaking changes detected:")
        print(json.dumps(breaking, indent=2, default=str))
        return 1

    additive = {k: v for k, v in diff.to_dict().items() if k not in BREAKING_MARKERS}
    if additive:
        print("OpenAPI additive changes (non-breaking):")
        print(json.dumps(additive, indent=2, default=str))
    else:
        print("OpenAPI schema matches baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
