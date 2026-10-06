import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from timestamps import to_epoch_seconds  # noqa: E402

EXPECTED = 1760000000


@pytest.mark.parametrize(
    "value",
    [
        datetime.fromtimestamp(EXPECTED, tz=timezone.utc),
        "2025-10-09T08:53:20+00:00",
        "2025-10-09T08:53:20Z",
        "2025-10-09T08:53:20.000Z",
        "2025-10-09T08:53:20",
        "2025-10-09T10:53:20+02:00",
    ],
)
def test_converts_datetimes_and_iso_strings(value):
    assert to_epoch_seconds(value) == EXPECTED


@pytest.mark.parametrize("value", [None, ""])
def test_empty_values_become_none(value):
    assert to_epoch_seconds(value) is None
