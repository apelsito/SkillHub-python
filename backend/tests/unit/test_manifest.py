import pytest

from skillhub_api.domain.skill import PackageError
from skillhub_api.services.skills.manifest import parse_manifest

VALID = """---
name: My Skill
description: Does a thing.
version: 1.2.3
---

# Body
paragraph text.
"""


def test_parse_valid_manifest() -> None:
    m = parse_manifest(VALID)
    assert m.name == "My Skill"
    assert m.description == "Does a thing."
    assert m.version == "1.2.3"
    assert "Body" in m.body


def test_manifest_without_frontmatter() -> None:
    with pytest.raises(PackageError, match="frontmatter"):
        parse_manifest("# just body")


def test_manifest_missing_required_field() -> None:
    source = "---\nname: no desc\n---\n"
    with pytest.raises(PackageError, match="description"):
        parse_manifest(source)


def test_manifest_invalid_yaml() -> None:
    source = "---\nname: bad\n  :\n---\n"
    with pytest.raises(PackageError):
        parse_manifest(source)


def test_manifest_version_optional() -> None:
    source = "---\nname: x\ndescription: y\n---\n"
    m = parse_manifest(source)
    assert m.version is None
