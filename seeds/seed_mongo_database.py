"""Seed the SIH SYNTHETIC DEMO DATABASE in MongoDB.

Recreates the eight ``borderverify`` collections with a coherent, fully-synthetic
(SIH demo) travel dataset.  Everything here is FAKE - no real passport, no real
national ID, no real watchlist - and is labelled ``SIH SYNTHETIC DEMO DATABASE`` /
``DEMO / MOCK``.

Run from project root::

    py -3.10 seeds/seed_mongo_database.py

Re-running is idempotent: it drops the working collections first, seeds fresh,
then creates indexes (including a unique index on passport_number).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

# Ensure the backend package is importable regardless of the CWD.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.config import settings                       # noqa: E402
from app.db.mongo import get_mongodb, ensure_indexes  # noqa: E402

NOW = datetime.utcnow()
TODAY = NOW.date()

DS = settings.DATA_SOURCE_LABEL


def iso(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


def days_ago(n: int) -> datetime.date:
    return TODAY - timedelta(days=n)


def days_ahead(n: int) -> datetime.date:
    return TODAY + timedelta(days=n)


# ---------------------------------------------------------------------------
# Scenario definitions (these align with the sample images)
# ---------------------------------------------------------------------------
# Each entry: dict of the synthetic passenger's core attributes.  Passports,
# visas, identities & watchlists are generated from these where relevant.

SCENARIO_PASSENGERS = [
    {
        "passenger_id": "PAX-0001", "surname": "SMITH", "given_names": "JOHN",
        "nationality": "USA", "date_of_birth": "1985-04-12", "sex": "M",
        "passport_number": "P1234567", "passport_status": "valid",
        "expiry": str(days_ahead(1300)), "status": "active",
        "risk_profile": "normal",
    },
    {
        "passenger_id": "PAX-0002", "surname": "BROWN", "given_names": "ALICE",
        "nationality": "GBR", "date_of_birth": "1990-11-05", "sex": "F",
        "passport_number": "P7654321", "passport_status": "expired",
        "expiry": str(days_ago(920)), "status": "active",
        "risk_profile": "normal",
    },
    {
        "passenger_id": "PAX-0003", "surname": "GREEN", "given_names": "CAROL",
        "nationality": "CAN", "date_of_birth": "1992-02-18", "sex": "F",
        "passport_number": "P2345678", "passport_status": "valid",
        "expiry": str(days_ahead(1500)), "visa_number": "VISA-0003",
        "visa_expiry": str(days_ago(40)), "status": "active",
        "risk_profile": "normal",
    },
    {
        "passenger_id": "PAX-0004", "surname": "JONES", "given_names": "MICHAEL",
        "nationality": "USA", "date_of_birth": "1988-07-23", "sex": "M",
        "passport_number": "P1111222", "passport_status": "valid",
        "expiry": str(days_ahead(900)), "status": "active",
        "risk_profile": "watchlisted", "watchlist": "STOLEN",
        "watchlist_reason": "Document reported stolen at border control.",
    },
    {
        "passenger_id": "PAX-0005", "surname": "WHITE", "given_names": "DAVID",
        "nationality": "IND", "date_of_birth": "1983-01-30", "sex": "M",
        "passport_number": "P9998887", "passport_status": "valid",
        "expiry": str(days_ahead(700)), "status": "active",
        "risk_profile": "normal",
    },
    {
        "passenger_id": "PAX-0006", "surname": "KUMAR", "given_names": "ROBERT",
        "nationality": "IND", "date_of_birth": "1995-09-14", "sex": "M",
        "passport_number": "P5556665", "passport_status": "valid",
        "expiry": str(days_ahead(1100)), "status": "active",
        "risk_profile": "duplicate", "alias_name": "KUMAR R",
    },
    {
        "passenger_id": "PAX-0007", "surname": "TAYLOR", "given_names": "HANNAH",
        "nationality": "AUS", "date_of_birth": "1991-05-02", "sex": "F",
        "passport_number": "P3333555", "passport_status": "valid",
        "expiry": str(days_ahead(800)), "status": "active",
        "risk_profile": "normal",
    },
    {
        "passenger_id": "PAX-0008", "surname": "PARKER", "given_names": "OLIVER",
        "nationality": "NZL", "date_of_birth": "1987-12-08", "sex": "M",
        "passport_number": "P7777888", "passport_status": "valid",
        "expiry": str(days_ahead(1600)), "status": "active",
        "risk_profile": "normal",
    },
    {
        # Used by the built-in demo "valid" scenario (verify_demo default doc no).
        "passenger_id": "PAX-0021", "surname": "JOHNSON", "given_names": "EMMA",
        "nationality": "USA", "date_of_birth": "1990-09-09", "sex": "F",
        "passport_number": "P12345678", "passport_status": "valid",
        "expiry": str(days_ahead(2100)), "status": "active",
        "risk_profile": "normal",
    },
]

# A few additional travellers to reach volume (passports + identities only).
BULK_PASSENGERS = [
    ("PAX-0009",  "MURPHY",   "LIAM",     "IRL", "1990-03-14", "M", "P1239998", days_ahead(2000)),
    ("PAX-0010",  "NGUYEN",   "LINH",     "VNM", "1994-06-21", "F", "P4567774", days_ahead(1200)),
    ("PAX-0011",  "SCHMIDT",  "LISA",     "DEU", "1986-10-09", "F", "P8882221", days_ahead(1800)),
    ("PAX-0012",  "ROSSI",    "MARCO",    "ITA", "1993-01-26", "M", "P2227779", days_ahead(950)),
    ("PAX-0013",  "DUBOIS",   "MARIE",    "FRA", "1989-04-17", "F", "P9993332", days_ahead(1400)),
    ("PAX-0014",  "SILVA",    "PEDRO",    "BRA", "1996-08-11", "M", "P4445556", days_ahead(760)),
    ("PAX-0015",  "YAMADA",   "AKI",      "JPN", "1992-12-05", "F", "P1237770", days_ahead(1750)),
    ("PAX-0016",  "MUELLER",  "HANS",     "CHE", "1984-05-28", "M", "P6543210", days_ahead(150)),
    ("PAX-0017",  "FERNANDEZ","SOFIA",    "ESP", "1995-02-14", "F", "P3219870", days_ahead(1050)),
    ("PAX-0018",  "PATEL",    "ARJUN",    "IND", "1990-07-07", "M", "P9090901", days_ahead(1300)),
    ("PAX-0019",  "O'BRIEN",  "KATE",     "IRL", "1991-03-31", "F", "P8080809", days_ahead(900)),
    ("PAX-0020",  "KOCH",     "EMMA",     "POL", "1993-11-19", "F", "P7070777", days_ahead(1250)),
]
BULK_MAX = 12  # passports for bulk passengers add up to 20 total passport records


# ---------------------------------------------------------------------------
# Generator helpers
# ---------------------------------------------------------------------------

def _ident_ref(idx: int) -> str:
    return f"ID-{idx:04d}-{datetime(NOW.year, 1, 1).strftime('%y%m')}"


def build_documents():
    """Return the dict of documents grouped by collection (for one seed pass)."""
    passengers = []
    passport_records = []
    visa_records = []
    watchlist_records = []
    identity_records = []
    verification_records = []
    audit_logs = []
    system_config = []

    # --- Scenario passengers ---
    all_passengers = list(SCENARIO_PASSENGERS)
    for i, (pid, surname, given, nat, dob, sex, pnum, expiry) in enumerate(BULK_PASSENGERS):
        all_passengers.append({
            "passenger_id": pid, "surname": surname, "given_names": given,
            "nationality": nat, "date_of_birth": dob, "sex": sex,
            "passport_number": pnum, "passport_status": "valid",
            "expiry": str(expiry), "status": "active", "risk_profile": "normal",
        })

    for idx, p in enumerate(all_passengers, start=1):
        pid = p["passenger_id"]
        full_name = f"{p['given_names']} {p['surname']}".strip()
        ident_ref = _ident_ref(idx)
        dob_iso = p["date_of_birth"]

        passengers.append({
            "passenger_id": pid, "full_name": full_name,
            "surname": p["surname"], "given_names": p["given_names"],
            "nationality": p["nationality"], "date_of_birth": dob_iso,
            "sex": p["sex"], "status": p.get("status", "active"),
            "identity_reference": ident_ref,
            "risk_profile": p.get("risk_profile", "normal"),
            "data_source": DS, "created_at": NOW,
        })

        # Passport
        pnum = p["passport_number"]
        pstatus = p.get("passport_status", "valid")
        issue = iso(days_ago(random_days(1200, 2500)))
        expiry = p.get("expiry")
        document_is_valid = pstatus == "valid"
        passport_records.append({
            "passport_number": pnum, "surname": p["surname"],
            "given_names": p["given_names"], "full_name": full_name,
            "nationality": p["nationality"], "date_of_birth": dob_iso,
            "sex": p["sex"], "passport_type": "P",
            "issuing_country": p["nationality"], "date_of_issue": issue,
            "date_of_expiry": expiry, "status": pstatus,
            "document_is_valid": document_is_valid, "passenger_id": pid,
            "data_source": DS, "created_at": NOW,
        })

        # Identity record (one per traveller; duplicate case gets an alias entry)
        identity_records.append({
            "identity_reference": ident_ref, "passenger_id": pid,
            "passport_number": pnum, "full_name": full_name,
            "surname": p["surname"], "given_names": p["given_names"],
            "date_of_birth": dob_iso, "nationality": p["nationality"],
            "risk_level": p.get("risk_profile", "normal"),
            "status": "active", "data_source": DS, "created_at": NOW,
        })
        if p.get("risk_profile") == "duplicate":
            # A second, *different* travel document for the same identity.  The
            # distinct document number is what lets dedupe flag a multiple-identity,
            # while the candidate's own record (same doc) is excluded.
            alias = p.get("alias_name", p["surname"])
            suffix = pnum[1:] if len(pnum) > 1 and pnum[0] == "P" else pnum
            alias_doc = "P" + str(int(suffix) + 1) if suffix.isdigit() else pnum + "A"
            identity_records.append({
                "identity_reference": _ident_ref(idx + 100), "passenger_id": pid,
                "passport_number": alias_doc, "full_name": f"{alias} {p['given_names'][0]}",
                "surname": alias, "given_names": p["given_names"][0],
                "date_of_birth": dob_iso, "nationality": p["nationality"],
                "risk_level": "duplicate", "status": "active",
                "data_source": DS, "created_at": NOW,
            })

        # Watchlist
        if p.get("watchlist"):
            watchlist_records.append({
                "passport_number": pnum, "reference_id": _ident_ref(idx + 200),
                "name": full_name, "surname": p["surname"],
                "given_names": p["given_names"], "date_of_birth": dob_iso,
                "category": p["watchlist"], "reason": p.get("watchlist_reason", "Listed."),
                "status": "active", "data_source": DS, "created_at": NOW,
            })

        # Visa (scenario-driven)
        if p.get("visa_number"):
            visa_records.append({
                "visa_number": p["visa_number"], "passport_number": pnum,
                "visa_type": "TOURIST", "issuing_country": p["nationality"],
                "issue_date": iso(days_ago(500)), "expiry_date": p.get("visa_expiry"),
                "status": "expired" if p.get("visa_expiry") and p["visa_expiry"] < iso(TODAY) else "valid",
                "data_source": DS, "created_at": NOW,
            })

    # A few more visas for volume
    extra_visas = [
        ("VISA-0101", "P1234567", "TOURIST", "USA", "2025-01-01", "2027-01-01", "valid"),
        ("VISA-0102", "P9998887", "TOURIST", "IND", "2025-02-01", "2026-08-01", "valid"),
        ("VISA-0103", "P5556665", "BUSINESS", "IND", "2025-03-01", "2027-03-01", "valid"),
        ("VISA-0104", "P3333555", "TOURIST", "AUS", "2025-01-15", "2026-10-15", "valid"),
        ("VISA-0105", "P7777888", "STUDENT", "NZL", "2024-06-01", "2026-06-01", "expired"),
        ("VISA-0106", "P1239998", "TOURIST", "IRL", "2025-04-01", "2027-04-01", "valid"),
        ("VISA-0107", "P4567774", "TOURIST", "VNM", "2025-05-01", "2027-05-01", "valid"),
        ("VISA-0108", "P8882221", "BUSINESS", "DEU", "2025-06-01", "2027-06-01", "valid"),
        ("VISA-0109", "P2227779", "TOURIST", "ITA", "2025-07-01", "2027-07-01", "valid"),
        ("VISA-0110", "P9993332", "TOURIST", "FRA", "2025-08-01", "2027-08-01", "valid"),
        ("VISA-0111", "P12345678", "TOURIST", "USA", "2025-09-01", "2027-09-01", "valid"),
    ]
    for v in extra_visas:
        visa_records.append({
            "visa_number": v[0], "passport_number": v[1], "visa_type": v[2],
            "issuing_country": v[3], "issue_date": v[4], "expiry_date": v[5],
            "status": v[6], "data_source": DS, "created_at": NOW,
        })

    # A few more watchlist entries for volume
    # Important: P1234567 (valid scenario), P9998887 (mismatch scenario),
    # P5556665 (duplicate scenario) are intentionally NOT watchlisted so each
    # demonstration case isolates its own risk signal.
    extra_watchlist = [
        ("P1239998", "DENIED", "MURPHY LIAM", "MURPHY", "LIAM", "1990-03-14",
         "Visa denied at a previous application."),
        ("P6543210", "WANTED", "MUELLER HANS", "MUELLER", "HANS", "1984-05-28",
         "Wanted for overstay (demo)."),
        ("P9090901", "STOLEN", "PATEL ARJUN", "PATEL", "ARJUN", "1990-07-07",
         "Document reported lost/stolen (demo)."),
        ("P7777888", "DENIED", "PARKER OLIVER", "PARKER", "OLIVER", "1987-12-08",
         "Attempted entry previously denied (demo)."),
    ]
    for (pnum, cat, name, sur, giv, dob, reason) in extra_watchlist:
        watchlist_records.append({
            "passport_number": pnum, "reference_id": _ident_ref(300 + len(watchlist_records)),
            "name": name, "surname": sur, "given_names": giv, "date_of_birth": dob,
            "category": cat, "reason": reason, "status": "active",
            "data_source": DS, "created_at": NOW,
        })

    # Historical verification + audit records (demo)
    for i in range(1, 6):
        vid = f"VER-{i:05d}"
        pnum = f"P123{400 + i:04d}"
        verification_records.append({
            "verification_id": vid, "passport_number": pnum,
            "passenger_id": f"PAX-0{i:02d}", "document_type": "passport",
            "decision": "VERIFIED", "risk_score": 0, "risk_level": "LOW",
            "officer_id": 1, "data_source": DS,
            "created_at": NOW - timedelta(days=i * 3),
        })
        audit_logs.append({
            "verification_id": vid, "officer_id": 1,
            "action": "document_verified", "detail": f"Synthetic verification #{i}.",
            "timestamp": NOW - timedelta(days=i * 3),
        })

    # System config / transparency metadata
    system_config = [
        {"key": "data_source_label", "value": DS, "note": "Label shown in the UI."},
        {"key": "environment", "value": settings.DATA_SOURCE_ENVIRONMENT,
         "note": "DEMO / MOCK - not production."},
        {"key": "government_integration", "value": settings.GOVERNMENT_INTEGRATION,
         "note": "No real government API is connected."},
        {"key": "future_integration", "value": settings.FUTURE_INTEGRATION,
         "note": "Planned authorised government API."},
        {"key": "mode", "value": "synthetic-demo",
         "note": "All records are synthetic; no real personal data."},
    ]

    return {
        "passengers": passengers,
        "passport_records": passport_records,
        "visa_records": visa_records,
        "watchlist_records": watchlist_records,
        "identity_records": identity_records,
        "verification_records": verification_records,
        "audit_logs": audit_logs,
        "system_config": system_config,
    }


def random_days(a: int, b: int) -> int:
    import random
    return random.randint(a, b)


def main() -> None:
    db = get_mongodb()
    docs = build_documents()

    # Reset the working collections (synthetic demo DB -> safe to reset).
    for name in docs:
        db[name].drop()

    for name, rows in docs.items():
        if rows:
            db[name].insert_many(rows)

    ensure_indexes()

    # Per-collection counts
    counts = {name: db[name].estimated_document_count() for name in docs}
    print("Seeded MongoDB database ->", settings.MONGODB_DATABASE)
    for name, c in counts.items():
        print(f"  {name}: {c}")


if __name__ == "__main__":
    main()
