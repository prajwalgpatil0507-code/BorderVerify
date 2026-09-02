"""MongoDB connection + collections for the SIH SYNTHETIC DEMO DATABASE.

This is a *local, synthetic* dataset used to simulate the reference data a real
border system would query (passports, visas, watchlist, identity records).  It is
NOT a government database and must always be labelled as DEMO / MOCK.

A single PyMongo ``MongoClient`` is reused across the app.  All connection
parameters come from environment variables so no credentials are hardcoded.
"""
from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from ..config import settings


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

COLLECTIONS = (
    "passengers",
    "passport_records",
    "visa_records",
    "watchlist_records",
    "identity_records",
    "verification_records",
    "audit_logs",
    "system_config",
)


@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """Return a shared MongoClient (lazy singleton)."""
    return MongoClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
    )


def get_mongodb() -> Database:
    """Return the ``borderverify`` database handle."""
    return get_mongo_client()[settings.MONGODB_DATABASE]


def get_collection(name: str):
    """Return a named collection from the working database."""
    return get_mongodb()[name]


def mongo_available() -> bool:
    """Best-effort connectivity check (never raises)."""
    try:
        get_mongodb().command("ping")
        return True
    except Exception:  # noqa: BLE001
        return False


def ping() -> dict:
    """Ping the database; raise if unreachable."""
    return get_mongodb().command("ping")


def database_name() -> str:
    return settings.MONGODB_DATABASE


# ---------------------------------------------------------------------------
# Indexes (created idempotently by the seed script and on app startup)
# ---------------------------------------------------------------------------

def ensure_indexes() -> None:
    """Create the important indexes; safe to call repeatedly."""
    db = get_mongodb()

    db.passengers.create_index("passenger_id", unique=True, sparse=True)
    db.passengers.create_index("identity_reference")

    db.passport_records.create_index("passport_number", unique=True, sparse=True)
    db.passport_records.create_index("passenger_id")
    db.passport_records.create_index("date_of_expiry")

    db.visa_records.create_index("visa_number", unique=True, sparse=True)
    db.visa_records.create_index("passport_number")

    db.watchlist_records.create_index("passport_number")
    db.watchlist_records.create_index("reference_id")

    db.identity_records.create_index("identity_reference", unique=True, sparse=True)
    db.identity_records.create_index("passenger_id")

    db.verification_records.create_index("verification_id", unique=True, sparse=True)
    db.verification_records.create_index("passport_number")
    db.verification_records.create_index("created_at")

    db.audit_logs.create_index("verification_id")
    db.audit_logs.create_index("timestamp")

    db.system_config.create_index("key", unique=True, sparse=True)


def counts() -> dict:
    """Return the number of documents per collection (for the demo page)."""
    db = get_mongodb()
    return {
        "passengers": db.passengers.estimated_document_count(),
        "passport_records": db.passport_records.estimated_document_count(),
        "visa_records": db.visa_records.estimated_document_count(),
        "watchlist_records": db.watchlist_records.estimated_document_count(),
        "identity_records": db.identity_records.estimated_document_count(),
        "verification_records": db.verification_records.estimated_document_count(),
    }
