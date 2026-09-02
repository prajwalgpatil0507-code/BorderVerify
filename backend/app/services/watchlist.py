"""DEMO watchlist / blacklist service.

This is a **synthetic, demo-only** dataset.  It does not access any real
government or law-enforcement database.  The architecture is designed so an
authorised government API adapter can be dropped in later behind the same
interface.  The UI must label this clearly as a demo watchlist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# Synthetic demo watchlist records. All names/numbers are fictional.
_DEMO_WATCHLIST: list[dict] = [
    {
        "document_number": "X99887766",
        "surname": "DEMOOS",
        "given_names": "WATCH",
        "date_of_birth": "850101",
        "nationality": "DMO",
        "reason": "Demo watchlist record (synthetic): overstay report.",
        "category": "watchlist",
    },
    {
        "document_number": "X11223344",
        "surname": "BANNED",
        "given_names": "ENTRY",
        "date_of_birth": "881212",
        "nationality": "DMO",
        "reason": "Demo watchlist record (synthetic): prior refusal of entry.",
        "category": "watchlist",
    },
    {
        "document_number": "N76543210",
        "surname": "FLAGGED",
        "given_names": "TRAVEL",
        "date_of_birth": "921012",
        "nationality": "IND",
        "reason": "Demo blacklist record (synthetic): suspected document fraud.",
        "category": "blacklist",
    },
    {
        "document_number": "Z55667788",
        "surname": "SUSPECT",
        "given_names": "ALIAS",
        "date_of_birth": "790707",
        "nationality": "UTO",
        "reason": "Demo watchlist record (synthetic): identity fraud investigation.",
        "category": "watchlist",
    },
]

# Demo "prior records" used by duplicate-identity detection. Synthetic only.
# These deliberately do NOT overlap with the "valid" demo passenger (RAIJILO)
# so a genuine passport is not falsely flagged as a duplicate identity.
_DEMO_EXISTING_RECORDS: list[dict] = [
    {
        "document_number": "P11223399",
        "surname": "KUMAR",
        "given_names": "RAHUL",
        "date_of_birth": "101003",
        "nationality": "IND",
        "face_descriptor_seed": "kumar_rahul",
    },
    {
        "document_number": "P55667788",
        "surname": "SHARMA",
        "given_names": "ANIL",
        "date_of_birth": "950808",
        "nationality": "IND",
        "face_descriptor_seed": "sharma_anil",
    },
]


@dataclass
class WatchlistResult:
    matched: bool
    category: str = ""
    reason: str = ""
    source: str = "DEMO"

    def to_dict(self) -> dict:
        return {
            "matched": self.matched,
            "category": self.category,
            "reason": self.reason,
            "source": self.source,
        }


def check_watchlist(document_number: str = "",
                    surname: str = "",
                    date_of_birth: str = "") -> WatchlistResult:
    """Check against the demo watchlist. Clear by default."""
    doc_norm = (document_number or "").upper().strip()
    sur_norm = (surname or "").upper().strip()
    dob_norm = (date_of_birth or "").strip()

    for rec in _DEMO_WATCHLIST:
        if doc_norm and doc_norm == rec["document_number"].upper():
            return WatchlistResult(matched=True, category=rec["category"],
                                   reason=rec["reason"])
        # Name + DOB fuzzy match for alias detection
        if sur_norm and sur_norm == rec["surname"].upper() and rec["date_of_birth"] == dob_norm:
            return WatchlistResult(matched=True, category=rec["category"],
                                   reason=rec["reason"] + " (name/DOB match)")

    return WatchlistResult(matched=False)


def get_demo_existing_records() -> list[dict]:
    return _DEMO_EXISTING_RECORDS
