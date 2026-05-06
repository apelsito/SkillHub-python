"""Dump the live FastAPI OpenAPI schema to a JSON file.

Used in CI to diff against ``openapi/java-baseline.json`` so changes that
break frontend contract compatibility fail the build.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: export_openapi.py <output.json>", file=sys.stderr)
        return 2

    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)

    from skillhub_api.main import app

    schema = app.openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
