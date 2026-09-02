"""Date and expiry validation utilities (dependency-free)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


def today() -> date:
    return date.today()


def expiry_status(expiry: Optional[date], expiring_soon_days: int = 180) -> dict:
    """Evaluate a document expiry date.

    Returns a dict with:
      * ``status``   -> "valid" | "expiring_soon" | "expired" | "unknown"
      * ``days_left`` -> int or None
      * ``explanation`` -> human readable string
    """
    if expiry is None:
        return {
            "status": "unknown",
            "days_left": None,
            "explanation": "Expiry date could not be determined.",
        }
    now = today()
    delta = (expiry - now).days
    if delta < 0:
        return {
            "status": "expired",
            "days_left": delta,
            "explanation": f"Document expired {-delta} day(s) ago.",
        }
    if delta <= expiring_soon_days:
        return {
            "status": "expiring_soon",
            "days_left": delta,
            "explanation": f"Document expires in {delta} day(s) (soon).",
        }
    return {
        "status": "valid",
        "days_left": delta,
        "explanation": f"Document valid for {delta} more day(s).",
    }


def parse_iso(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None
