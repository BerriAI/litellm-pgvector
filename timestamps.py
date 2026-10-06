from datetime import datetime, timezone
from typing import Optional, Union


def to_epoch_seconds(value: Union[datetime, str, None]) -> Optional[int]:
    """Convert a raw-query timestamp to Unix seconds.

    Prisma's query_raw can hand back timestamp columns as datetime objects or
    as ISO-8601 strings. Strings without an offset are read as UTC.
    """
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())
