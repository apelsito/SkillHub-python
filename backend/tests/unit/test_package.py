import io
import zipfile

import pytest

from skillhub_api.domain.skill import PackageError
from skillhub_api.services.skills.package import extract_package, slugify


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_extract_valid_package() -> None:
    manifest = b"---\nname: Valid\ndescription: d\nversion: 1.0.0\n---\nbody"
    main_py = b"print('hi')"
    zip_bytes = _zip({"SKILL.md": manifest, "src/main.py": main_py})
    pkg = extract_package(zip_bytes)
    assert pkg.file_count == 2
    assert pkg.total_size == len(manifest) + len(main_py)
    assert all(len(f.sha256) == 64 for f in pkg.files)


def test_extract_missing_manifest() -> None:
    with pytest.raises(PackageError, match=r"SKILL\.md"):
        extract_package(_zip({"src/a.py": b"x"}))


def test_extract_rejects_traversal() -> None:
    with pytest.raises(PackageError):
        extract_package(
            _zip({"../escape.md": b"x", "SKILL.md": b"---\nname: x\ndescription: y\n---\n"})
        )


def test_extract_rejects_bad_extension() -> None:
    with pytest.raises(PackageError):
        extract_package(
            _zip(
                {
                    "SKILL.md": b"---\nname: x\ndescription: y\n---\n",
                    "malware.exe": b"MZ",
                }
            )
        )


def test_extract_rejects_large_single_file() -> None:
    big = b"x" * (10 * 1024 * 1024 + 1)
    with pytest.raises(PackageError, match="exceeds"):
        extract_package(_zip({"SKILL.md": b"---\nname: x\ndescription: y\n---\n", "big.txt": big}))


def test_slugify_normalises() -> None:
    assert slugify("My Cool Skill!") == "my-cool-skill"
    assert slugify("  Trim Me  ") == "trim-me"


def test_slugify_rejects_non_alnum_only() -> None:
    with pytest.raises(PackageError):
        slugify("!!!")
