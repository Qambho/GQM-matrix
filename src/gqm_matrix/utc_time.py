"""Centralized UTC time provider — all components use London (UTC+0)."""

from __future__ import annotations

from datetime import datetime, timezone


class UtcTimeProvider:
    """Always returns timezone-aware UTC timestamps."""

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def iso_now() -> str:
        return UtcTimeProvider.now().isoformat()


utc_provider = UtcTimeProvider()
