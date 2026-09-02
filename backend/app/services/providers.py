"""Demo data providers - query the SIH DEMO DATABASE.

In a production border system the verification pipeline would query authorised
government/agency APIs.  For the SIH prototype we simulate those external data
sources with a local database.  These providers isolate that concern behind
clean interfaces (``DemoPassportProvider``, ``DemoVisaProvider``,
``DemoWatchlistProvider``, ``DemoIdentityProvider``) so the live verification
workflow reads from the SIH DEMO DATABASE instead of a hardcoded in-memory list.

Every provider only reads the corresponding DEMO table; no real government data
is ever accessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import settings
from ..models.models import (SessionLocal, PassportRecord, VisaRecord,
                             WatchlistRecord, IdentityRecord)
from ..db import mongo as mongo
from . import dedupe as dedupe_service


# Labels used to mark every result as coming from the synthetic demo dataset.
SOURCE_LABEL = settings.DATA_SOURCE_LABEL
ENVIRONMENT = settings.DATA_SOURCE_ENVIRONMENT


def _use_mongo() -> bool:
    """Use the MongoDB-backed providers only if Mongo is reachable."""
    try:
        return mongo.mongo_available()
    except Exception:  # noqa: BLE001
        return False


def _query(fn):
    """Run ``fn(session)`` inside a short-lived session that always closes."""
    db = SessionLocal()
    try:
        return fn(db)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------

@dataclass
class PassportLookup:
    found: bool = False
    status: str = ""
    document_number: str = ""
    surname: str = ""
    given_names: str = ""
    nationality: str = ""
    date_of_birth: str = ""
    date_of_issue: str = ""
    date_of_expiry: str = ""
    issuing_country: str = ""
    anomaly: bool = False          # status/stolen flag -> document_anomaly signal
    source: str = SOURCE_LABEL
    environment: str = ENVIRONMENT
    table: str = "passport_records"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class VisaLookup:
    found: bool = False
    status: str = ""
    visa_number: str = ""
    visa_type: str = ""
    issuing_country: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    document_number: str = ""
    source: str = SOURCE_LABEL
    environment: str = ENVIRONMENT
    table: str = "visa_records"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class WatchlistMatch:
    matched: bool = False
    category: str = ""
    reason: str = ""
    source: str = "DEMO"
    environment: str = ENVIRONMENT
    table: str = "watchlist_records"

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class DuplicateLookup:
    """Wraps a dedupe result and adds demo provenance."""
    result: dedupe_service.DuplicateResult
    source: str = SOURCE_LABEL
    environment: str = ENVIRONMENT
    table: str = "identity_records"

    @property
    def is_duplicate(self) -> bool:
        return self.result.is_duplicate

    @property
    def confidence(self) -> float:
        return self.result.confidence

    def to_dict(self) -> dict:
        d = self.result.to_dict()
        d["source"] = self.source
        d["environment"] = self.environment
        d["table"] = self.table
        return d


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

class DemoPassportProvider:
    """Look up a document number in the (demo) issued-passport registry."""

    def lookup(self, document_number: str) -> PassportLookup:
        doc = (document_number or "").strip().upper()

        def _find(db):
            return (db.query(PassportRecord)
                    .filter(PassportRecord.document_number == doc).first())

        rec = _query(_find)
        if not rec:
            return PassportLookup(found=False, document_number=doc)
        return PassportLookup(
            found=True, status=rec.status, document_number=rec.document_number,
            surname=rec.surname, given_names=rec.given_names,
            nationality=rec.nationality, date_of_birth=rec.date_of_birth,
            date_of_issue=rec.date_of_issue, date_of_expiry=rec.date_of_expiry,
            issuing_country=rec.issuing_country,
        )


class DemoVisaProvider:
    """Look up a document number in the (demo) visa registry."""

    def lookup(self, document_number: str) -> VisaLookup:
        doc = (document_number or "").strip().upper()

        def _find(db):
            return (db.query(VisaRecord)
                    .filter(VisaRecord.document_number == doc).first())

        rec = _query(_find)
        if not rec:
            return VisaLookup(found=False, document_number=doc)
        return VisaLookup(
            found=True, status=rec.status, visa_number=rec.visa_number,
            visa_type=rec.visa_type, issuing_country=rec.issuing_country,
            issue_date=rec.issue_date, expiry_date=rec.expiry_date,
            document_number=rec.document_number,
        )


class DemoWatchlistProvider:
    """Check a document / identity against the (demo) watchlist & blacklist."""

    def check(self, document_number: str = "", surname: str = "",
              date_of_birth: str = "") -> WatchlistMatch:
        doc_norm = (document_number or "").upper().strip()
        sur_norm = (surname or "").upper().strip()
        dob_norm = (date_of_birth or "").strip()

        def _find(db):
            rows = db.query(WatchlistRecord).all()
            for rec in rows:
                if doc_norm and doc_norm == rec.document_number.upper():
                    return rec, False
                if sur_norm and sur_norm == rec.surname.upper() and rec.date_of_birth == dob_norm:
                    return rec, True
            return None, False

        rec, via_name = _query(_find)
        if not rec:
            return WatchlistMatch(matched=False)
        reason = rec.reason
        if via_name:
            reason += " (name/DOB match)"
        return WatchlistMatch(matched=True, category=rec.category, reason=reason)


class DemoIdentityProvider:
    """Check the candidate against prior-traveller (demo) records for duplicates."""

    def check(self, attrs: dict, face_score: Optional[float] = None) -> DuplicateLookup:
        own_doc = (attrs.get("document_number", "") or "").upper().strip()

        def _records(db):
            prior = []
            for r in db.query(IdentityRecord).all():
                rec_doc = (r.document_number or "").upper().strip()
                if own_doc and rec_doc == own_doc:
                    continue
                prior.append({
                    "document_number": r.document_number, "surname": r.surname,
                    "given_names": r.given_names, "date_of_birth": r.date_of_birth,
                    "nationality": r.nationality,
                })
            return prior

        prior = _query(_records)
        result = dedupe_service.check_duplicates(attrs, face_score=face_score,
                                                 prior_records=prior)
        return DuplicateLookup(result=result)


# ---------------------------------------------------------------------------
# MongoDB-backed providers (SIH SYNTHETIC DEMO DATABASE)
# ---------------------------------------------------------------------------
# These read the same 5 collections the demo SQLite providers read, but from the
# REAL local MongoDB server so the live upload pipeline demonstrates a genuine
# database lookup.  The provider interfaces are identical, so neither the
# orchestrator nor the results shape changes.
#
#   passport_records   -> MongoPassportProvider
#   visa_records       -> MongoVisaProvider
#   watchlist_records  -> MongoWatchlistProvider
#   identity_records   -> MongoIdentityProvider
# ---------------------------------------------------------------------------

class MongoPassportProvider:
    """Look up a document number in the MongoDB passport registry."""

    def lookup(self, document_number: str) -> PassportLookup:
        doc = (document_number or "").strip().upper()
        if not doc:
            return PassportLookup(found=False, document_number=doc)
        rec = mongo.get_collection("passport_records").find_one(
            {"passport_number": doc})
        if not rec:
            return PassportLookup(found=False, document_number=doc)
        status = str(rec.get("status", "") or "").lower()
        document_is_valid = bool(rec.get("document_is_valid", True))
        anomaly = (not document_is_valid) or status in ("stolen", "suspicious", "reported")
        return PassportLookup(
            found=True, status=status, document_number=rec.get("passport_number", doc),
            surname=rec.get("surname", ""), given_names=rec.get("given_names", ""),
            nationality=rec.get("nationality", ""), date_of_birth=rec.get("date_of_birth", ""),
            date_of_issue=rec.get("date_of_issue", ""), date_of_expiry=rec.get("date_of_expiry", ""),
            issuing_country=rec.get("issuing_country", ""),
            anomaly=anomaly,
            table="passport_records",
        )


class MongoVisaProvider:
    """Look up a document number in the MongoDB visa registry."""

    def lookup(self, document_number: str) -> VisaLookup:
        doc = (document_number or "").strip().upper()
        if not doc:
            return VisaLookup(found=False, document_number=doc)
        rec = mongo.get_collection("visa_records").find_one(
            {"passport_number": doc})
        if not rec:
            return VisaLookup(found=False, document_number=doc)
        return VisaLookup(
            found=True, status=rec.get("status", ""), visa_number=rec.get("visa_number", ""),
            visa_type=rec.get("visa_type", ""), issuing_country=rec.get("issuing_country", ""),
            issue_date=rec.get("issue_date", ""), expiry_date=rec.get("expiry_date", ""),
            document_number=rec.get("passport_number", doc),
            table="visa_records",
        )


class MongoWatchlistProvider:
    """Check a document / identity against the MongoDB watchlist & blacklist."""

    def check(self, document_number: str = "", surname: str = "",
              date_of_birth: str = "") -> WatchlistMatch:
        doc_norm = (document_number or "").upper().strip()
        sur_norm = (surname or "").upper().strip()
        dob_norm = (date_of_birth or "").strip()
        col = mongo.get_collection("watchlist_records")

        rec_id = None
        via_name = False
        if doc_norm:
            rec = col.find_one({"passport_number": doc_norm,
                                "status": {"$in": ["active", "flagged"]}})
            if rec:
                rec_id = rec
        if rec_id is None and sur_norm:
            rec = col.find_one({"surname": sur_norm, "date_of_birth": dob_norm,
                                "status": {"$in": ["active", "flagged"]}})
            if rec:
                rec_id = rec
                via_name = True

        if not rec_id:
            return WatchlistMatch(matched=False)
        reason = str(rec_id.get("reason", "listed"))
        if via_name:
            reason += " (name/DOB match)"
        category = str(rec_id.get("category", "watchlist")).lower()
        return WatchlistMatch(matched=True, category=category, reason=reason,
                              table="watchlist_records")


class MongoIdentityProvider:
    """Check the candidate against prior-traveller (Mongo) records for duplicates."""

    def check(self, attrs: dict, face_score: Optional[float] = None) -> DuplicateLookup:
        col = mongo.get_collection("identity_records")
        own_doc = (attrs.get("document_number", "") or "").upper().strip()
        prior = []
        for rec in col.find({}, {"_id": 0}):
            rec_doc = (rec.get("passport_number", "") or "").upper().strip()
            # The candidate's OWN authoritative record is not a duplicate.
            if own_doc and rec_doc == own_doc:
                continue
            prior.append({
                "document_number": rec.get("passport_number", ""),
                "surname": rec.get("surname", ""),
                "given_names": rec.get("given_names", ""),
                "date_of_birth": rec.get("date_of_birth", ""),
                "nationality": rec.get("nationality", ""),
            })
        result = dedupe_service.check_duplicates(attrs, face_score=face_score,
                                                 prior_records=prior)
        return DuplicateLookup(result=result, table="identity_records")


# ---------------------------------------------------------------------------
# Provider factory (the orchestrator calls these, so the storage backend can be
# swapped without touching the pipeline).
# ---------------------------------------------------------------------------

_current_backend = {"kind": None}


def backend_kind() -> str:
    """Return 'mongodb' when Mongo is available, else 'sqlite'."""
    if _current_backend["kind"] is None:
        _current_backend["kind"] = "mongodb" if _use_mongo() else "sqlite"
    return _current_backend["kind"]


def get_passport_provider():
    return MongoPassportProvider() if backend_kind() == "mongodb" else DemoPassportProvider()


def get_visa_provider():
    return MongoVisaProvider() if backend_kind() == "mongodb" else DemoVisaProvider()


def get_watchlist_provider():
    return MongoWatchlistProvider() if backend_kind() == "mongodb" else DemoWatchlistProvider()


def get_identity_provider():
    return MongoIdentityProvider() if backend_kind() == "mongodb" else DemoIdentityProvider()


def _build_source_block(checks: list[dict]) -> dict:
    """Describe the storage backend that each verification check queried."""
    backend = backend_kind()
    return {
        "backend": backend,
        "label": SOURCE_LABEL,
        "environment": ENVIRONMENT,
        "is_real_data": False,
        "checks": checks,
    }
