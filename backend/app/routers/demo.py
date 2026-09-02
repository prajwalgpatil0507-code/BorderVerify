"""Read-only endpoints that expose the SIH DEMO DATABASE.

These routes simulate the *external data sources* a real border verification
system would query (watchlist, visa registry, travel history, stolen-lost
document register).  All records are synthetic and are clearly labelled as
DEMO / MOCK DATA.  Nothing here represents a real government database.

All endpoints are deliberately SELECT-only and require an authenticated officer,
mirroring the rest of the protected API.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..models.models import (get_db, Officer, DemoMeta, WatchlistRecord,
                             VisaRecord, TravelRecord, StolenLostDocument,
                             PassportRecord, IdentityRecord)
from ..core.deps import get_current_officer

router = APIRouter(tags=["demo"])

LABEL = "SIH DEMO DATABASE"
DATASET_TYPE = "DEMO / MOCK DATA"


def _disclaimer(db: Session) -> str:
    row = db.query(DemoMeta).filter(DemoMeta.key == "disclaimer").first()
    if row and row.value:
        return row.value
    return (
        "DEMO / MOCK DATA. This dataset is fictional and synthetic, generated for "
        "the Smart India Hackathon prototype. It is NOT a real government, police, "
        "or immigration database."
    )


def _records_to_dicts(rows) -> list[dict]:
    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns
             if c.name not in ("created_at", "id")}
        d["source"] = "DEMO"
        out.append(d)
    return out


@router.get("/demo/metadata")
async def demo_metadata(officer: Officer = Depends(get_current_officer),
                        db: Session = Depends(get_db)):
    """Return the dataset identity + label + counts."""
    source_counts = {
        "watchlist_records": db.query(WatchlistRecord).count(),
        "visa_records": db.query(VisaRecord).count(),
        "travel_history": db.query(TravelRecord).count(),
        "stolen_lost_documents": db.query(StolenLostDocument).count(),
        "passport_records": db.query(PassportRecord).count(),
        "identity_records": db.query(IdentityRecord).count(),
    }
    return {
        "label": LABEL,
        "dataset_type": DATASET_TYPE,
        "is_demo": True,
        "is_real_data": False,
        "disclaimer": _disclaimer(db),
        "version": "1.0.0",
        "sources": source_counts,
    }


@router.get("/demo/data-sources")
async def demo_data_sources(officer: Officer = Depends(get_current_officer),
                            db: Session = Depends(get_db)):
    """List every simulated source with counts + a small sample of records."""
    def source(name: str, description: str, query, sample_limit: int = 5) -> dict:
        rows = query.all()
        return {
            "name": name,
            "index": name,
            "description": description,
            "is_demo": True,
            "count": len(rows),
            "sample_records": _records_to_dicts(rows[:sample_limit]),
        }

    return {
        "label": LABEL,
        "dataset_type": DATASET_TYPE,
        "is_demo": True,
        "disclaimer": _disclaimer(db),
        "sources": [
            source("watchlist_records", "Law-enforcement watchlist & blacklist",
                   db.query(WatchlistRecord)),
            source("visa_records", "Visa registry (validity / overstay check)",
                   db.query(VisaRecord)),
            source("travel_history", "Arrival / departure movement log",
                   db.query(TravelRecord).order_by(TravelRecord.document_number,
                                                   TravelRecord.timestamp)),
            source("stolen_lost_documents", "Stolen & Lost Travel Document (SLTD) register",
                   db.query(StolenLostDocument)),
            source("passport_records", "Issued-passport registry (document-of-issue look-up)",
                   db.query(PassportRecord)),
            source("identity_records", "Prior-traveller records (duplicate-identity check)",
                   db.query(IdentityRecord)),
        ],
    }


@router.get("/demo/lookup/{document_number}")
async def demo_lookup(document_number: str,
                      officer: Officer = Depends(get_current_officer),
                      db: Session = Depends(get_db)):
    """Simulate looking up a traveller against all external data sources.

    Returns, for each source, whether a matching record exists in the demo
    dataset.  This is what a real border system would do behind the scenes.
    """
    doc = document_number.strip().upper()
    if not doc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="document_number is required")

    records = {}

    wl = (db.query(WatchlistRecord)
          .filter(WatchlistRecord.document_number == doc).first())
    records["watchlist"] = {"matched": wl is not None,
                            "records": _records_to_dicts([wl]) if wl else []}

    vis = (db.query(VisaRecord)
           .filter(VisaRecord.document_number == doc).all())
    records["visa"] = {"matched": bool(vis),
                       "records": _records_to_dicts(vis)}

    tr = (db.query(TravelRecord)
          .filter(TravelRecord.document_number == doc)
          .order_by(TravelRecord.timestamp).all())
    records["travel_history"] = {"matched": bool(tr),
                                 "records": _records_to_dicts(tr)}

    sl = (db.query(StolenLostDocument)
          .filter(StolenLostDocument.document_number == doc).first())
    records["stolen_lost"] = {"matched": sl is not None,
                              "records": _records_to_dicts([sl]) if sl else []}

    pp = (db.query(PassportRecord)
          .filter(PassportRecord.document_number == doc).first())
    records["passport"] = {"matched": pp is not None,
                           "records": _records_to_dicts([pp]) if pp else []}

    rec = (db.query(IdentityRecord)
           .filter(IdentityRecord.document_number == doc).first())
    records["identity"] = {"matched": rec is not None,
                           "records": _records_to_dicts([rec]) if rec else []}

    matched_sources = [k for k, v in records.items() if v["matched"]]

    return {
        "label": LABEL,
        "dataset_type": DATASET_TYPE,
        "is_demo": True,
        "document_number": doc,
        "matched_sources": matched_sources,
        "summary": (
            f"Simulated look-up found {len(matched_sources)} matching source(s) "
            f"for {doc}." if matched_sources else
            f"Simulated look-up found no matches for {doc}."
        ),
        "sources": records,
    }


@router.get("/demo/travellers")
async def demo_travellers(officer: Officer = Depends(get_current_officer),
                          db: Session = Depends(get_db)):
    """Per-traveller consolidated demo view (useful for the judge demo)."""
    # Collect distinct document numbers present across the reference tables.
    docs: set[str] = set()
    for model in (WatchlistRecord, VisaRecord, TravelRecord, StolenLostDocument):
        docs.update(x.document_number for x in db.query(model).all())

    travellers = []
    for doc in sorted(docs):
        entry = {"document_number": doc, "is_demo": True, "sources": {}}
        wl = (db.query(WatchlistRecord)
              .filter(WatchlistRecord.document_number == doc).first())
        entry["sources"]["watchlist"] = wl.reason if wl else None
        vis = (db.query(VisaRecord)
               .filter(VisaRecord.document_number == doc).first())
        entry["sources"]["visa"] = vis.status if vis else "none"
        counts = {
            "arrival": db.query(TravelRecord)
            .filter(TravelRecord.document_number == doc,
                    TravelRecord.event_type == "arrival").count(),
            "departure": db.query(TravelRecord)
            .filter(TravelRecord.document_number == doc,
                    TravelRecord.event_type == "departure").count(),
        }
        entry["sources"]["travel_history"] = counts
        sl = (db.query(StolenLostDocument)
              .filter(StolenLostDocument.document_number == doc).first())
        entry["sources"]["stolen_lost"] = sl.status if sl else None
        travellers.append(entry)

    return {"label": LABEL, "dataset_type": DATASET_TYPE, "is_demo": True,
            "disclaimer": _disclaimer(db), "count": len(travellers),
            "travellers": travellers}
