"""Seed the SIH DEMO DATABASE with realistic (fictional) reference data.

Every record here is synthetic.  The tables populated simulate the *external
data sources* a real border / immigration verification system would query:

  * watchlist_records      -> law-enforcement watchlist & blacklist
  * visa_records           -> visa registry (validity / overstay check)
  * travel_history         -> arrival / departure movement log
  * stolen_lost_documents  -> Stolen & Lost Travel Document (SLTD) register
  * passport_records       -> issued-passport registry (document-of-issue look-up)
  * identity_records       -> prior-traveller records (duplicate-identity check)
  * demo_metadata          -> labels this whole dataset as DEMO / MOCK DATA

Nothing here touches a real government, police, or immigration database.  Run
this script any number of times - it is idempotent (it resets the four reference
tables and re-inserts the canonical demo rows each run).

Usage (from the project root):
    python seeds/seed_demo_database.py
"""
from __future__ import annotations

import os
import sys
import traceback

# Make `app` importable when run as a script from the repository root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from app.models.models import (  # noqa: E402
    Base, engine, SessionLocal, seed_demo_metadata,
    WatchlistRecord, VisaRecord, TravelRecord, StolenLostDocument,
    PassportRecord, IdentityRecord,
)


# ---------------------------------------------------------------------------
# Canonical demo dataset (all fictional)
# ---------------------------------------------------------------------------

# Law-enforcement watchlist / blacklist (source = DEMO)
WATCHLIST: list[dict] = [
    {"document_number": "X99887766", "surname": "DEMOOS", "date_of_birth": "850101",
     "category": "watchlist",
     "reason": "Demo watchlist record (synthetic): overstay report."},
    {"document_number": "X11223344", "surname": "BANNED", "date_of_birth": "881212",
     "category": "watchlist",
     "reason": "Demo watchlist record (synthetic): prior refusal of entry."},
    {"document_number": "N76543210", "surname": "FLAGGED", "date_of_birth": "921012",
     "category": "blacklist",
     "reason": "Demo blacklist record (synthetic): suspected document fraud."},
    {"document_number": "Z55667788", "surname": "SUSPECT", "date_of_birth": "790707",
     "category": "watchlist",
     "reason": "Demo watchlist record (synthetic): identity fraud investigation."},
    {"document_number": "K33221144", "surname": "REDFLAG", "date_of_birth": "601115",
     "category": "watchlist",
     "reason": "Demo watchlist record (synthetic): active immigration alert."},
    {"document_number": "G90817263", "surname": "DENIED", "date_of_birth": "740910",
     "category": "blacklist",
     "reason": "Demo blacklist record (synthetic): prior deportation order."},
]

# Visa registry (source = DEMO). expiry_date/issue_date are YYMMDD.
VISAS: list[dict] = [
    {"document_number": "P12345678", "visa_number": "VISA-2026-0001",
     "visa_type": "tourism", "issuing_country": "UTO",
     "issue_date": "260301", "expiry_date": "330912", "status": "valid"},
    {"document_number": "P11223399", "visa_number": "VISA-2023-4412",
     "visa_type": "business", "issuing_country": "IND",
     "issue_date": "230815", "expiry_date": "251201", "status": "expired"},
    {"document_number": "P55667788", "visa_number": "VISA-2025-8801",
     "visa_type": "tourism", "issuing_country": "IND",
     "issue_date": "251005", "expiry_date": "281005", "status": "valid"},
    {"document_number": "A98765432", "visa_number": "VISA-2024-9902",
     "visa_type": "student", "issuing_country": "USA",
     "issue_date": "240701", "expiry_date": "270701", "status": "valid"},
]

# Arrival / departure movement history (source = DEMO). timestamp is YYMMDDHHMM.
TRAVEL_HISTORY: list[dict] = [
    # RAIJILO (P12345678) - clean traveller, two trips.
    {"document_number": "P12345678", "event_type": "arrival",
     "port_code": "DEL", "country": "IND", "timestamp": "2506012210"},
    {"document_number": "P12345678", "event_type": "departure",
     "port_code": "DXB", "country": "ARE", "timestamp": "2506250815"},
    {"document_number": "P12345678", "event_type": "arrival",
     "port_code": "DEL", "country": "IND", "timestamp": "2601011000"},
    # KUMAR RAHUL (P11223399) - arrived, never departed, visa now expired -> overstay.
    {"document_number": "P11223399", "event_type": "arrival",
     "port_code": "BOM", "country": "IND", "timestamp": "2511010530"},
    # SHARMA ANIL (P55667788) - clean traveller.
    {"document_number": "P55667788", "event_type": "arrival",
     "port_code": "BLR", "country": "IND", "timestamp": "2508151200"},
    {"document_number": "P55667788", "event_type": "departure",
     "port_code": "SIN", "country": "SGP", "timestamp": "2509021845"},
]

# Stolen & Lost Travel Document register (source = DEMO).
STOLEN_LOST: list[dict] = [
    {"document_number": "A12345678", "document_type": "passport",
     "status": "STOLEN", "reported_date": "260505", "issuing_country": "UTO"},
    {"document_number": "B76543210", "document_type": "passport",
     "status": "LOST", "reported_date": "250101", "issuing_country": "FRA"},
]

# Issued-passport registry (source = DEMO). date_of_expiry is YYMMDD.
PASSPORTS: list[dict] = [
    {"document_number": "P12345678", "surname": "RAIJILO", "given_names": "MARK THOMAS",
     "date_of_birth": "000504", "nationality": "UTO", "date_of_issue": "240504",
     "date_of_expiry": "330912", "issuing_country": "UTO", "status": "valid"},
    {"document_number": "X99887766", "surname": "DEMOOS", "given_names": "WATCH",
     "date_of_birth": "850101", "nationality": "DMO", "date_of_issue": "230101",
     "date_of_expiry": "330101", "issuing_country": "DMO", "status": "valid"},
    {"document_number": "P11223399", "surname": "KUMAR", "given_names": "RAHUL",
     "date_of_birth": "101003", "nationality": "IND", "date_of_issue": "210101",
     "date_of_expiry": "330101", "issuing_country": "IND", "status": "valid"},
    {"document_number": "P55667788", "surname": "SHARMA", "given_names": "ANIL",
     "date_of_birth": "950808", "nationality": "IND", "date_of_issue": "220202",
     "date_of_expiry": "330101", "issuing_country": "IND", "status": "valid"},
    {"document_number": "A12345678", "surname": "PETROV", "given_names": "ALEX",
     "date_of_birth": "870612", "nationality": "UTO", "date_of_issue": "200303",
     "date_of_expiry": "330101", "issuing_country": "UTO", "status": "valid"},
]

# Prior-traveller records used for duplicate-identity detection (source = DEMO).
# Deliberately does NOT include RAIJILO (P12345678) so a genuine passport is not
# falsely flagged as a duplicate identity.
IDENTITIES: list[dict] = [
    {"document_number": "P11223399", "surname": "KUMAR", "given_names": "RAHUL",
     "date_of_birth": "101003", "nationality": "IND"},
    {"document_number": "P55667788", "surname": "SHARMA", "given_names": "ANIL",
     "date_of_birth": "950808", "nationality": "IND"},
    {"document_number": "P99887766", "surname": "GUPTA", "given_names": "SONU",
     "date_of_birth": "901212", "nationality": "IND"},
    {"document_number": "A98765432", "surname": "PETROV", "given_names": "ALEX",
     "date_of_birth": "870612", "nationality": "UTO"},
]


def _reset_and_insert(db) -> dict:
    """Clear + re-insert each reference table. Returns per-table counts."""
    counts = {}

    db.query(WatchlistRecord).delete()
    for r in WATCHLIST:
        db.add(WatchlistRecord(source="DEMO", **r))
    counts["watchlist_records"] = len(WATCHLIST)

    db.query(VisaRecord).delete()
    for r in VISAS:
        db.add(VisaRecord(source="DEMO", **r))
    counts["visa_records"] = len(VISAS)

    db.query(TravelRecord).delete()
    for r in TRAVEL_HISTORY:
        db.add(TravelRecord(source="DEMO", **r))
    counts["travel_history"] = len(TRAVEL_HISTORY)

    db.query(StolenLostDocument).delete()
    for r in STOLEN_LOST:
        db.add(StolenLostDocument(source="DEMO", **r))
    counts["stolen_lost_documents"] = len(STOLEN_LOST)

    db.query(PassportRecord).delete()
    for r in PASSPORTS:
        db.add(PassportRecord(source="DEMO", **r))
    counts["passport_records"] = len(PASSPORTS)

    db.query(IdentityRecord).delete()
    for r in IDENTITIES:
        db.add(IdentityRecord(source="DEMO", **r))
    counts["identity_records"] = len(IDENTITIES)

    db.commit()
    return counts


def main() -> int:
    print("=" * 70)
    print("  SIH DEMO DATABASE  -  DEMO / MOCK DATA")
    print("  Fictional synthetic records only. Not a real government source.")
    print("=" * 70)

    try:
        Base.metadata.create_all(bind=engine)
        with SessionLocal() as db:
            seed_demo_metadata(db)
            counts = _reset_and_insert(db)
        print("\nSeeded reference tables:")
        for name, count in counts.items():
            print(f"  {name:<22} {count}")
        print("\nDemo dataset ready at: "
              f"{os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'border_verify.db'))}")
        return 0
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
