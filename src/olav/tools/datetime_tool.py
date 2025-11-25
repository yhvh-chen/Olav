"""Natural language time range parsing tool."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from langchain_core.tools import tool


@tool
def parse_time_range(natural_text: str, now_iso: bool = True) -> tuple[str, str]:
    """Convert natural language time description into an ISO8601 time range.

    Supported phrases (simplified):
      'last night', 'past N hours', 'past N days', 'yesterday'
    Falls back to past 24h if unrecognized.

    Args:
        natural_text: Description like 'past 2 hours'.
        now_iso: If True return UTC Z suffix.

    Returns:
        (start_iso, end_iso)
    """
    now = datetime.now(UTC)
    text = natural_text.lower().strip()

    start: datetime
    end: datetime = now

    if "last night" in text or "昨晚" in text:
        # Approx: previous day 18:00 to current day 06:00 UTC
        yesterday = now - timedelta(days=1)
        start = yesterday.replace(hour=18, minute=0, second=0, microsecond=0)
        end = now.replace(hour=6, minute=0, second=0, microsecond=0)
    elif text.startswith("past ") and " hour" in text:
        # Extract numeric hours
        hours = "".join(ch for ch in text if ch.isdigit())
        h = int(hours or 24)
        start = now - timedelta(hours=h)
    elif text.startswith("past ") and " day" in text:
        days = "".join(ch for ch in text if ch.isdigit())
        d = int(days or 1)
        start = now - timedelta(days=d)
    elif "yesterday" in text or "昨天" in text:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    else:
        start = now - timedelta(days=1)

    fmt = "%Y-%m-%dT%H:%M:%SZ" if now_iso else "%Y-%m-%dT%H:%M:%S"
    return start.strftime(fmt), end.strftime(fmt)
