"""Shared date helpers for hotel booking tools."""

from __future__ import annotations

from datetime import date


def parse_date(value: str) -> date | str:
    """Parse an ISO date string, returning an error message string on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        return f"Invalid date '{value}'. Use YYYY-MM-DD format."


def format_date(d: date) -> str:
    """Format a date as 'Mon DD' for voice-friendly output."""
    return d.strftime("%b %d")
