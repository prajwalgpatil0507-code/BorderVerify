"""Read-only endpoints that expose the MongoDB-backed SIH SYNTHETIC DEMO DATABASE.

These routes power the "Demo Database" page and make the verification reference
data transparent.  Like the SQLite demo router, everything here is synthetic and
labelled DEMO / MOCK - it is NOT a real government database.

Every endpoint requires an authenticated officer.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..core.deps import get_current_officer
from ..db import mongo as mongo

router = APIRouter(tags=["database"])

COLLECTION_SELF = {
    "passengers": "Traveller profile (demographic) records",
    "passport_records": "Issued-passport registry (document-of-issue look-up)",
    "visa_records": "Visa registry (validity / overstay check)",
    "watchlist_records": "Law-enforcement watchlist & blacklist",
    "identity_records": "Prior-traveller records (duplicate-identity check)",
    "verification_records": "Historical verification outcomes",
    "audit_logs": "Officer audit trail",
    "system_config": "Dataset identity / metadata",
}


def _lite(doc: dict, max_keys: int = 8) -> dict:
    """Return a compact, JSON-safe version of a Mongo document."""
    if not isinstance(doc, dict):
        return doc
    out = {}
    for k, v in list(doc.items()):
        if k == "_id":
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
        if len(out) >= max_keys:
            break
    return out


@router.get("/database/overview")
async def database_overview(officer=Depends(get_current_officer)):
    """Dataset identity + storage backend + per-collection counts."""
    backend = mongo.database_name()
    return {
        "label": settings.DATA_SOURCE_LABEL,
        "environment": settings.DATA_SOURCE_ENVIRONMENT,
        "government_integration": settings.GOVERNMENT_INTEGRATION,
        "future_integration": settings.FUTURE_INTEGRATION,
        "is_demo": True,
        "is_real_data": False,
        "storage": "MongoDB" if mongo.mongo_available() else "UNAVAILABLE",
        "database": backend,
        "counts": mongo.counts() if mongo.mongo_available() else {},
        "disclaimer": (
            "DEMO / MOCK DATA. This dataset is fictional and synthetic, generated "
            "for the Smart India Hackathon prototype. It is NOT a real government, "
            "police, or immigration database."
        ),
    }


@router.get("/database/collections")
async def database_collections(officer=Depends(get_current_officer)):
    """List each collection with a short description, count, and a small sample."""
    collections = []
    for name, desc in COLLECTION_SELF.items():
        col = mongo.get_collection(name)
        count = col.estimated_document_count()
        sample = [_lite(d) for d in col.find({}).limit(3)]
        collections.append({
            "name": name,
            "description": desc,
            "count": count,
            "sample_records": sample,
        })
    return {
        "label": settings.DATA_SOURCE_LABEL,
        "environment": settings.DATA_SOURCE_ENVIRONMENT,
        "is_demo": True,
        "storage": "MongoDB" if mongo.mongo_available() else "UNAVAILABLE",
        "collections": collections,
    }


@router.get("/database/lookup/{document_number}")
async def database_lookup(document_number: str,
                          officer=Depends(get_current_officer)):
    """Look up a document number against the MongoDB reference collections."""
    doc = document_number.strip().upper()
    if not doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="document_number is required")

    def find(col: str, key: str):
        col_obj = mongo.get_collection(col)
        rec = col_obj.find_one({key: doc})
        return _lite(rec) if rec else None

    results = {
        "passport": find("passport_records", "passport_number"),
        "visa": find("visa_records", "passport_number"),
        "watchlist": find("watchlist_records", "passport_number"),
        "identity": find("identity_records", "passport_number"),
        "passenger": find("passengers", "passport_number"),
    }
    matched_sources = [k for k, v in results.items() if v]

    return {
        "label": settings.DATA_SOURCE_LABEL,
        "environment": settings.DATA_SOURCE_ENVIRONMENT,
        "is_demo": True,
        "document_number": doc,
        "matched_sources": matched_sources,
        "summary": (
            f"MongoDB look-up found {len(matched_sources)} matching source(s) "
            f"for {doc}." if matched_sources else
            f"MongoDB look-up found no matches for {doc}."
        ),
        "results": results,
    }


@router.get("/database/system-config")
async def database_system_config(officer=Depends(get_current_officer)):
    """Return the dataset metadata stored in system_config."""
    rows = list(mongo.get_collection("system_config").find({}))
    return {
        "label": settings.DATA_SOURCE_LABEL,
        "environment": settings.DATA_SOURCE_ENVIRONMENT,
        "is_demo": True,
        "config": [_lite(r, 6) for r in rows],
    }
