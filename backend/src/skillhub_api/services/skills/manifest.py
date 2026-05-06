"""Skill manifest parsing.

Ports ``SkillMetadataParser.java``: the manifest lives in ``SKILL.md`` as
YAML frontmatter delimited by ``---``. Required fields: ``name``,
``description``. If ``version`` is missing, callers auto-generate a
timestamp version (``yyyyMMdd.HHmmss``).

We parse strict YAML; the Java loose fallback is rarely exercised and left
out intentionally to avoid silently accepting malformed manifests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import yaml

from skillhub_api.domain.skill import PackageError

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class SkillManifest:
    name: str
    description: str
    version: str | None
    body: str
    frontmatter: dict[str, Any]


def parse_manifest(source: str) -> SkillManifest:
    match = _FRONTMATTER_RE.match(source)
    if match is None:
        raise PackageError("MANIFEST_NO_FRONTMATTER", "SKILL.md missing YAML frontmatter")
    raw_yaml, body = match.group(1), match.group(2)

    try:
        data = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise PackageError("MANIFEST_INVALID_YAML", f"SKILL.md YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise PackageError("MANIFEST_INVALID_YAML", "SKILL.md frontmatter must be a mapping")

    name = _require_str(data, "name")
    description = _require_str(data, "description")
    version = data.get("version")
    if version is not None and not isinstance(version, str):
        version = str(version)
    return SkillManifest(
        name=name.strip(),
        description=description.strip(),
        version=version.strip() if isinstance(version, str) else None,
        body=body,
        frontmatter=data,
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PackageError(
            "MANIFEST_MISSING_FIELD", f"SKILL.md frontmatter missing required field: {key}"
        )
    return value
