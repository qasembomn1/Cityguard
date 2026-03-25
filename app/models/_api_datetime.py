from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Any, Optional


def to_api_iso_text(value: Any, default_timezone: tzinfo) -> Optional[str]:
    if value in (None, ""):
        return None

    parsed: Optional[datetime]
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_timezone)

    parsed_utc = parsed.astimezone(timezone.utc)
    return parsed_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
