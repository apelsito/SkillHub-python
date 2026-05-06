import pytest

from skillhub_api.domain.skill import (
    ALLOWED_EXTENSIONS,
    PackageError,
    storage_key_for_bundle,
    storage_key_for_file,
    validate_extension,
    validate_relative_path,
)


@pytest.mark.parametrize(
    "good",
    ["skill.md", "SKILL.md", "src/main.py", "docs/readme.md", "a/b/c/d.txt"],
)
def test_valid_relative_paths(good: str) -> None:
    # Canonical form should round-trip.
    assert validate_relative_path(good) == good.lstrip("./")


@pytest.mark.parametrize(
    "bad",
    ["/etc/passwd", "C:/windows/system32", "../escape.md", "a/../b.md", "a//b.md"],
)
def test_invalid_relative_paths_rejected(bad: str) -> None:
    with pytest.raises(PackageError):
        validate_relative_path(bad)


def test_validate_extension_accepts_allowed() -> None:
    for ext in [".py", ".md", ".yaml", ".png", ".docx"]:
        assert ext in ALLOWED_EXTENSIONS
        validate_extension(f"foo{ext}")


def test_validate_extension_rejects_unknown() -> None:
    with pytest.raises(PackageError):
        validate_extension("malware.exe")
    with pytest.raises(PackageError):
        validate_extension("archive.tar")


def test_storage_keys_shape() -> None:
    assert storage_key_for_file(42, 7, "src/a.py") == "skills/42/7/src/a.py"
    assert storage_key_for_bundle(42, 7) == "packages/42/7/bundle.zip"


def test_allowed_extensions_matches_java_count() -> None:
    # Count derived from SkillPackagePolicy.java — guard against accidental
    # drift if extensions are added or removed without updating both sides.
    assert len(ALLOWED_EXTENSIONS) == 48
