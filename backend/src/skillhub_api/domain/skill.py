"""Skill domain enums + package policy + pure helpers.

Ports ``SkillPackagePolicy.java``. The exact allowed-extensions list is
load-bearing for security (scanner relies on the set) — keep in sync with
Java if it ever changes.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import PurePosixPath


class Visibility(StrEnum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    NAMESPACE_ONLY = "NAMESPACE_ONLY"


class SkillStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class SkillVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    UPLOADED = "UPLOADED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    YANKED = "YANKED"


MAX_FILE_COUNT = 500
MAX_SINGLE_FILE_SIZE = 10 * 1024 * 1024
MAX_TOTAL_PACKAGE_SIZE = 100 * 1024 * 1024

# 42 extensions from SkillPackagePolicy.java. Stored as a frozenset for O(1) checks.
ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".html",
        ".css",
        ".csv",
        ".pdf",
        ".toml",
        ".xml",
        ".xsd",
        ".xsl",
        ".dtd",
        ".ini",
        ".cfg",
        ".env",
        ".js",
        ".cjs",
        ".mjs",
        ".ts",
        ".py",
        ".sh",
        ".rb",
        ".go",
        ".rs",
        ".java",
        ".kt",
        ".lua",
        ".sql",
        ".r",
        ".bat",
        ".ps1",
        ".zsh",
        ".bash",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".gif",
        ".webp",
        ".ico",
        ".doc",
        ".xls",
        ".ppt",
        ".docx",
        ".xlsx",
        ".pptx",
    }
)

MANIFEST_FILENAME = "SKILL.md"


class PackageError(ValueError):
    """Raised when a submitted file path violates policy.

    Carries an error code so the router layer can translate into the
    structured Java-compatible error body.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_relative_path(raw: str) -> str:
    """Validate a zip entry path and return its canonical form.

    Mirrors SkillPackagePolicy.java:39-68:
      * normalize backslashes to forward slashes
      * reject absolute paths, null bytes, drive letters
      * reject ``..`` traversal
      * require canonical form == input after normalize
    """
    if not raw or "\x00" in raw:
        raise PackageError("INVALID_PATH", f"invalid path: {raw!r}")
    normalized = raw.replace("\\", "/").strip()
    if normalized.startswith("/"):
        raise PackageError("ABSOLUTE_PATH", f"absolute path not allowed: {raw!r}")
    # Windows drive letter (c:/...).
    if len(normalized) >= 2 and normalized[1] == ":":
        raise PackageError("ABSOLUTE_PATH", f"drive-letter path not allowed: {raw!r}")
    parts = PurePosixPath(normalized).parts
    if any(part == ".." for part in parts):
        raise PackageError("PATH_TRAVERSAL", f"path traversal not allowed: {raw!r}")
    canonical = "/".join(p for p in parts if p not in ("", "."))
    if canonical != normalized.lstrip("./"):
        # Reject inputs that normalize to something different (e.g. trailing
        # slashes, embedded `.` segments).
        raise PackageError("NON_CANONICAL_PATH", f"non-canonical path: {raw!r}")
    return canonical


def validate_extension(path: str) -> None:
    ext = PurePosixPath(path).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise PackageError("EXTENSION_NOT_ALLOWED", f"extension {ext!r} not allowed")


def storage_key_for_file(skill_id: int, version_id: int, relative_path: str) -> str:
    """Storage key for an individual file — ``skills/{skill}/{version}/{path}``."""
    return f"skills/{skill_id}/{version_id}/{relative_path}"


def storage_key_for_bundle(skill_id: int, version_id: int) -> str:
    """Storage key for the bundle zip — ``packages/{skill}/{version}/bundle.zip``."""
    return f"packages/{skill_id}/{version_id}/bundle.zip"
