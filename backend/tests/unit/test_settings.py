from datetime import timedelta

import pytest

from skillhub_api.settings import _iso_duration


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("PT10M", timedelta(minutes=10)),
        ("PT8H", timedelta(hours=8)),
        ("PT30S", timedelta(seconds=30)),
        ("PT2M", timedelta(minutes=2)),
        ("P30D", timedelta(days=30)),
        ("PT1H30M", timedelta(hours=1, minutes=30)),
    ],
)
def test_iso_duration_parses_common_values(value: str, expected: timedelta) -> None:
    assert _iso_duration(value) == expected


def test_iso_duration_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        _iso_duration("10 minutes")
