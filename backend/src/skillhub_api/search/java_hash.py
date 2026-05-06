"""Java ``String.hashCode()`` reimplementation.

Python's built-in ``str.__hash__`` is salted (PYTHONHASHSEED) and not
stable across processes. The Java contract is:

    s[0]*31^(n-1) + s[1]*31^(n-2) + ... + s[n-1]

evaluated with 32-bit signed integer overflow over **UTF-16 code units**
(so supplementary code points contribute a surrogate pair).

Reproducing it exactly is load-bearing for the embedding service,
because stored vectors need the same bucket mapping to remain comparable
across languages.
"""

from __future__ import annotations


def _utf16_code_units(text: str) -> list[int]:
    encoded = text.encode("utf-16-be")
    return [(encoded[i] << 8) | encoded[i + 1] for i in range(0, len(encoded), 2)]


def java_string_hashcode(text: str) -> int:
    """Return the Java ``String.hashCode`` of ``text`` as a 32-bit signed int."""
    h = 0
    for code_unit in _utf16_code_units(text):
        # Wrap after each multiply-add so behavior matches Java's int overflow.
        h = (h * 31 + code_unit) & 0xFFFFFFFF
    # Reduce to signed 32-bit range.
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def java_floor_mod(value: int, modulus: int) -> int:
    """Port of ``Math.floorMod``.

    Python's ``%`` already matches Java when the modulus is positive (the
    result is non-negative) — so this wrapper is here to document intent
    and guard against a refactor that forgets the contract.
    """
    if modulus <= 0:
        raise ValueError("modulus must be positive")
    return value % modulus
