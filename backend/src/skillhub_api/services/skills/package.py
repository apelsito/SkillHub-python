"""Skill package extraction + validation.

Reads an in-memory zip, enforces ``SkillPackagePolicy`` limits, and yields
each (relative_path, bytes) pair. The caller (publish service) then hashes,
uploads to storage, and writes DB rows.
"""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass

from skillhub_api.domain.skill import (
    MANIFEST_FILENAME,
    MAX_FILE_COUNT,
    MAX_SINGLE_FILE_SIZE,
    MAX_TOTAL_PACKAGE_SIZE,
    PackageError,
    validate_extension,
    validate_relative_path,
)


@dataclass(frozen=True, slots=True)
class ExtractedFile:
    path: str
    data: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ExtractedPackage:
    manifest_source: str
    files: list[ExtractedFile]

    @property
    def total_size(self) -> int:
        return sum(len(f.data) for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)


def extract_package(zip_bytes: bytes) -> ExtractedPackage:
    if len(zip_bytes) > MAX_TOTAL_PACKAGE_SIZE:
        raise PackageError(
            "PACKAGE_TOO_LARGE",
            f"package exceeds {MAX_TOTAL_PACKAGE_SIZE} bytes",
        )

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise PackageError("INVALID_ZIP", "package is not a valid zip archive") from exc

    files: list[ExtractedFile] = []
    manifest_source: str | None = None
    seen_paths: set[str] = set()
    total_size = 0

    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            path = validate_relative_path(info.filename)
            if path in seen_paths:
                raise PackageError("DUPLICATE_PATH", f"duplicate path in zip: {path}")
            seen_paths.add(path)

            if info.file_size > MAX_SINGLE_FILE_SIZE:
                raise PackageError(
                    "FILE_TOO_LARGE",
                    f"{path} exceeds {MAX_SINGLE_FILE_SIZE} bytes",
                )
            validate_extension(path)

            data = zf.read(info)
            if len(data) > MAX_SINGLE_FILE_SIZE:
                raise PackageError(
                    "FILE_TOO_LARGE",
                    f"{path} exceeds {MAX_SINGLE_FILE_SIZE} bytes after decompression",
                )
            total_size += len(data)
            if total_size > MAX_TOTAL_PACKAGE_SIZE:
                raise PackageError(
                    "PACKAGE_TOO_LARGE",
                    f"package exceeds {MAX_TOTAL_PACKAGE_SIZE} bytes uncompressed",
                )

            sha = hashlib.sha256(data).hexdigest()
            files.append(ExtractedFile(path=path, data=data, sha256=sha))

            if path == MANIFEST_FILENAME:
                manifest_source = data.decode("utf-8")

            if len(files) > MAX_FILE_COUNT:
                raise PackageError(
                    "TOO_MANY_FILES",
                    f"package exceeds {MAX_FILE_COUNT} files",
                )

    if manifest_source is None:
        raise PackageError("MANIFEST_MISSING", f"{MANIFEST_FILENAME} not found in package")
    return ExtractedPackage(manifest_source=manifest_source, files=files)


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Mirror Java's slug generation: lowercase, ASCII alnum + dash, trimmed."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        raise PackageError("INVALID_SLUG", f"cannot derive slug from name: {name!r}")
    return slug[:128]
