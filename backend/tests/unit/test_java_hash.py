"""Golden-file tests for the Java String.hashCode port.

Values were computed by running

    jshell
    > "hello".hashCode()

on Java 21 and recorded here. Any drift in ``java_string_hashcode`` will
break interoperability with existing Java-written semantic vectors, so
these assertions must stay exact.
"""

import pytest

from skillhub_api.search.java_hash import java_floor_mod, java_string_hashcode


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Empty / ASCII-only — values well-known from the Java Javadoc.
        ("", 0),
        ("a", 97),
        ("hello", 99162322),
        ("Hello", 69609650),
        ("hello world", 1794106052),
        ("skillhub", 2142461188),
        ("SKILL.md", -1369903500),
        ("abc123_-", 1211005502),
        # Additional ASCII samples with negative and positive JVM results.
        ("cafe", 3045789),
        ("resume", -934426579),
    ],
)
def test_java_string_hashcode_matches_jvm(text: str, expected: int) -> None:
    assert java_string_hashcode(text) == expected


def test_java_floor_mod_matches_java_on_negatives() -> None:
    # Math.floorMod(-7, 64) == 57.
    assert java_floor_mod(-7, 64) == 57
    assert java_floor_mod(0, 64) == 0
    assert java_floor_mod(65, 64) == 1


def test_java_floor_mod_rejects_non_positive_modulus() -> None:
    with pytest.raises(ValueError):
        java_floor_mod(1, 0)
    with pytest.raises(ValueError):
        java_floor_mod(1, -5)
