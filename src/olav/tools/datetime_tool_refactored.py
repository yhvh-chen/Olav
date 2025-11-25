"""Time range parsing tool refactored to BaseTool protocol.

This module provides natural language time range parsing functionality.
Converts phrases like 'past 2 hours' or 'yesterday' to ISO8601 time ranges.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta

from olav.tools.base import BaseTool, ToolOutput

logger = logging.getLogger(__name__)


class TimeRangeTool(BaseTool):
    """Convert natural language time description into ISO8601 time range.

    Supports phrases like:
    - 'last night', '昨晚' (previous day 18:00 to current day 06:00 UTC)
    - 'past N hours' (N hours ago to now)
    - 'past N days' (N days ago to now)
    - 'yesterday', '昨天' (previous day 00:00 to 23:59)

    Falls back to past 24 hours if phrase is unrecognized.
    """

    def __init__(self) -> None:
        """Initialize time range parsing tool."""
        self._name = "parse_time_range"
        self._description = (
            "Convert natural language time description into ISO8601 time range. "
            "Supports phrases like 'past 2 hours', 'yesterday', 'last night', etc. "
            "Returns (start_iso, end_iso) tuple."
        )

    @property
    def name(self) -> str:
        """Tool name for registration."""
        return self._name

    @property
    def description(self) -> str:
        """Tool description for LLM."""
        return self._description

    async def execute(
        self,
        natural_text: str,
        utc_format: bool = True,
    ) -> ToolOutput:
        """Parse natural language time description to ISO8601 range.

        Args:
            natural_text: Description like 'past 2 hours', 'yesterday', 'last night'.
            utc_format: If True, return UTC with 'Z' suffix (default: True).

        Returns:
            ToolOutput with data containing {"start": start_iso, "end": end_iso}.

        Examples:
            >>> result = await tool.execute("past 2 hours")
            >>> result.data
            {"start": "2024-01-15T08:00:00Z", "end": "2024-01-15T10:00:00Z"}

            >>> result = await tool.execute("yesterday")
            >>> result.data
            {"start": "2024-01-14T00:00:00Z", "end": "2024-01-15T00:00:00Z"}
        """
        start_time = time.perf_counter()

        # Validate parameters
        if not natural_text or not natural_text.strip():
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": 0, "error_type": "param_error"},
                error="natural_text parameter cannot be empty",
            )

        try:
            now = datetime.now(UTC)
            text = natural_text.lower().strip()

            start: datetime
            end: datetime = now
            recognized_pattern = "unknown"

            # Pattern matching
            if "last night" in text or "昨晚" in text:
                # Previous day 18:00 to current day 06:00 UTC
                yesterday = now - timedelta(days=1)
                start = yesterday.replace(hour=18, minute=0, second=0, microsecond=0)
                end = now.replace(hour=6, minute=0, second=0, microsecond=0)
                recognized_pattern = "last_night"

            elif text.startswith("past ") and " hour" in text:
                # Extract numeric hours
                hours_str = "".join(ch for ch in text if ch.isdigit())
                hours = int(hours_str or 24)
                start = now - timedelta(hours=hours)
                recognized_pattern = f"past_{hours}_hours"

            elif text.startswith("past ") and " day" in text:
                # Extract numeric days
                days_str = "".join(ch for ch in text if ch.isdigit())
                days = int(days_str or 1)
                start = now - timedelta(days=days)
                recognized_pattern = f"past_{days}_days"

            elif "yesterday" in text or "昨天" in text:
                # Previous day 00:00 to 23:59
                start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                end = start + timedelta(days=1)
                recognized_pattern = "yesterday"

            else:
                # Fallback: past 24 hours
                start = now - timedelta(days=1)
                recognized_pattern = "fallback_24h"
                logger.warning(
                    f"Unrecognized time phrase '{natural_text}', falling back to past 24 hours"
                )

            # Format to ISO8601
            fmt = "%Y-%m-%dT%H:%M:%SZ" if utc_format else "%Y-%m-%dT%H:%M:%S"
            start_iso = start.strftime(fmt)
            end_iso = end.strftime(fmt)

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[
                    {
                        "start": start_iso,
                        "end": end_iso,
                        "duration_hours": (end - start).total_seconds() / 3600,
                    }
                ],
                metadata={
                    "natural_text": natural_text,
                    "recognized_pattern": recognized_pattern,
                    "utc_format": utc_format,
                    "elapsed_ms": elapsed_ms,
                },
                error=None,
            )

        except ValueError as e:
            # Handle integer parsing errors
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "param_error"},
                error=f"Invalid time phrase format: {e}",
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Time range parsing failed")
            return ToolOutput(
                source=self.name,
                device="unknown",
                data=[],
                metadata={"elapsed_ms": elapsed_ms, "error_type": "param_error"},
                error=f"Time parsing error: {e}",
            )


# Tool is auto-registered on module import but can be created independently for testing
# _time_range_tool = TimeRangeTool()
