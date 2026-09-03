"""Seed the SIH SYNTHETIC DEMO DATABASE with reference records.

This is the "reference data" the verification pipeline queries to decide whether a
presented document is genuinely valid.  A real border system would query an
authorised government agency registry; for the prototype we simulate those
registries with a clearly-labelled DEMO / MOCK dataset.

Every record here is FICTIONAL.  These records are written to BOTH storage
backends so the live upload pipeline performs a genuine database look-up:

  * MongoDB  (primary; survives container redeploys when a database is configured)
  * SQLite   (fallback / offline local development)

The document numbers below intentionally match the built-in sample images (see
``data/samples/*.png``) so a real upload of one of those images extracts the same
number, looks it up against these records, and produces a genuine VERIFIED /
NOT VERIFIED / UNVERIFIED verdict.  Nothing here is real government data.
"""
from __future__ import annotations

import logging

from ..config import settings
from ..models.models import (PassportRecord, VisaRecord, WatchlistRecord,
                             IdentityRecord, SessionLocal)
from ..db import mongo as mongo

logger = logging.getLogger("borderverify.seed")

# ---------------------------------------------------------------------------
# Reference records (synthetic / DEMO only)
# ---------------------------------------------------------------------------
# ``date_of_*`` are stored as YYMMDD strings (the format the MRZ uses) so the
# look-up and the upstream field comparison agree.

PASSPORT_RECORDS = [
    # Matches valid_passport.png / mismatch_passport.png / expired_passport.png
    {
        "passport_number": "P12345678",
        "surname": "RAIJILO",
        "given_names": "MARK THOMAS",
        "date_of_birth": "000504",
        "nationality": "UTO",
        "date_of_issue": "240504",
        "date_of_expiry": "330912",
        "issuing_country": "UTO",
        "status": "valid",
        "document_is_valid": True,
    },
    # Matches watchlist_passport.png (watchlisted traveller)
    {
        "passport_number": "X99887766",
        "surname": "SILVA",
        "given_names": "MARIA",
        "date_of_birth": "850101",
        "nationality": "DMO",
        "date_of_issue": "200511",
        "date_of_expiry": "330101",
        "issuing_country": "DMO",
        "status": "valid",
        "document_is_valid": True,
    },
    # Demo watchlist scenario (JONES / MICHAEL)
    {
        "passport_number": "P1111222",
        "surname": "JONES",
        "given_names": "MICHAEL",
        "date_of_birth": "880723",
        "nationality": "USA",
        "date_of_issue": "210314",
        "date_of_expiry": "330101",
        "issuing_country": "USA",
        "status": "valid",
        "document_is_valid": True,
    },
    # Demo duplicate-identity scenario (KUMAR / ROBERT)
    {
        "passport_number": "P5556665",
        "surname": "KUMAR",
        "given_names": "ROBERT",
        "date_of_birth": "950914",
        "nationality": "IND",
        "date_of_issue": "220607",
        "date_of_expiry": "330101",
        "issuing_country": "IND",
        "status": "valid",
        "document_is_valid": True,
    },
]

VISA_RECORDS = [
    {
        "passport_number": "P12345678",
        "visa_number": "V123456",
        "visa_type": "D",
        "issuing_country": "UTO",
        "issue_date": "240504",
        "expiry_date": "330912",
        "status": "valid",
    },
]

WATCHLIST_RECORDS = [
    # The watchlist_passport.png traveller is on the (mock) blacklist.
    {
        "passport_number": "X99887766",
        "surname": "SILVA",
        "date_of_birth": "850101",
        "category": "blacklist",
        "reason": "Stolen/lost document travelling under a high-risk holder.",
        "status": "active",
    },
    # Demo watchlist scenario passenger.
    {
        "passport_number": "P1111222",
        "surname": "JONES",
        "date_of_birth": "880723",
        "category": "watchlist",
        "reason": "Flagged on the (mock) border watch list.",
        "status": "active",
    },
]

IDENTITY_RECORDS = [
    # A prior-traveller record so the duplicate-identity check has data to find.
    {   # Same identity as P5556665 but under a different prior document.
        "passport_number": "PA9999999",
        "surname": "KUMAR",
        "given_names": "ROBERT",
        "date_of_birth": "950914",
        "nationality": "IND",
    },
    {   # Another prior-traveller (different identity) - not a duplicate.
        "passport_number": "PH8765432",
        "surname": "CHEN",
        "given_names": "LI WEI",
        "date_of_birth": "900203",
        "nationality": "PRC",
    },
]


# ---------------------------------------------------------------------------
# SQLite seeding (fallback / offline)
# ---------------------------------------------------------------------------

def _seed_sqlite() -> int:
    """Upsert reference records into the SQLite tables.

    Existing records are updated to the canonical ground-truth values (so a stale
    or mis-seeded row is corrected), and missing records are inserted. Returns the
    number of records newly added.
    """
    added = 0
    with SessionLocal() as db:
        for rec in PASSPORT_RECORDS:
            row = db.query(PassportRecord).filter(
                PassportRecord.document_number == rec["passport_number"]).first()
            fields = {
                "document_number": rec["passport_number"], "surname": rec["surname"],
                "given_names": rec["given_names"], "date_of_birth": rec["date_of_birth"],
                "nationality": rec["nationality"], "date_of_issue": rec["date_of_issue"],
                "date_of_expiry": rec["date_of_expiry"], "issuing_country": rec["issuing_country"],
                "status": rec["status"],
            }
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                db.add(PassportRecord(**fields))
                added += 1
        for rec in VISA_RECORDS:
            row = db.query(VisaRecord).filter(
                VisaRecord.document_number == rec["passport_number"]).first()
            fields = {
                "document_number": rec["passport_number"], "visa_number": rec["visa_number"],
                "visa_type": rec["visa_type"], "issuing_country": rec["issuing_country"],
                "issue_date": rec["issue_date"], "expiry_date": rec["expiry_date"],
                "status": rec["status"],
            }
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                db.add(VisaRecord(**fields))
                added += 1
        for rec in WATCHLIST_RECORDS:
            row = db.query(WatchlistRecord).filter(
                WatchlistRecord.document_number == rec["passport_number"]).first()
            fields = {
                "document_number": rec["passport_number"], "surname": rec["surname"],
                "date_of_birth": rec["date_of_birth"], "category": rec["category"],
                "reason": rec["reason"],
            }
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                db.add(WatchlistRecord(**fields))
                added += 1
        for rec in IDENTITY_RECORDS:
            row = db.query(IdentityRecord).filter(
                IdentityRecord.document_number == rec["passport_number"]).first()
            fields = {
                "document_number": rec["passport_number"], "surname": rec["surname"],
                "given_names": rec["given_names"], "date_of_birth": rec["date_of_birth"],
                "nationality": rec["nationality"],
            }
            if row:
                for k, v in fields.items():
                    setattr(row, k, v)
            else:
                db.add(IdentityRecord(**fields))
                added += 1
        db.commit()
    return added


# ---------------------------------------------------------------------------
# MongoDB seeding (primary persistence)
# ---------------------------------------------------------------------------

def _insert_many_upsert(collection_name: str, records: list[dict], key: str) -> int:
    """Upsert reference records so they always reflect the canonical ground truth.

    Uses ``$set`` rather than ``$setOnInsert``: if a record was previously seeded
    (or mis-seeded) with outdated identity data, re-seeding overwrites it with the
    authoritative value instead of leaving a stale / conflicting record in place.
    This is what makes the demo registry behave like a real reference database —
    the stored record for a given document number is deterministic and matches the
    sample document ground truth.

    Returns the number of records that were newly inserted.
    """
    col = mongo.get_collection(collection_name)
    written = 0
    for rec in records:
        res = col.update_one(
            {key: rec.get(key)},
            {"$set": rec},
            upsert=True,
        )
        if res.upserted_id is not None:
            written += 1
    return written


def _seed_mongo() -> int:
    """Insert reference records into MongoDB if absent. Returns count written."""
    written = 0
    for rec in PASSPORT_RECORDS:
        written += _insert_many_upsert("passport_records", [rec], "passport_number")
    for rec in VISA_RECORDS:
        written += _insert_many_upsert("visa_records", [rec], "passport_number")
    for rec in WATCHLIST_RECORDS:
        written += _insert_many_upsert("watchlist_records", [rec], "passport_number")
    for rec in IDENTITY_RECORDS:
        written += _insert_many_upsert("identity_records", [rec], "passport_number")
    return written


def seed_reference_data() -> dict:
    """Seed reference records into every reachable backend. Never raises.

    Returns a small report of what was added to each backend.
    """
    report = {"sqlite": 0, "mongodb": 0, "mongodb_available": False}
    try:
        report["sqlite"] = _seed_sqlite()
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite reference seed failed: %s", exc)

    try:
        if mongo.mongo_available():
            report["mongodb_available"] = True
            report["mongodb"] = _seed_mongo()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MongoDB reference seed failed: %s", exc)

    logger.info("Reference seed report: %s", report)
    return report
