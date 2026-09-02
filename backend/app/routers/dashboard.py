"""Dashboard statistics route."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from ..core.deps import get_current_officer
from ..models.models import get_db, Officer, VerificationSession
from ..config import settings

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/statistics")
async def dashboard_statistics(officer: Officer = Depends(get_current_officer),
                               db: Session = Depends(get_db)):
    q = db.query(VerificationSession)
    total = q.count()
    verified = q.filter(VerificationSession.decision == "VERIFIED").count()
    review = q.filter(VerificationSession.decision == "REVIEW REQUIRED").count()
    high = q.filter(VerificationSession.decision == "HIGH RISK").count()
    fraud = q.filter(and_(VerificationSession.decision == "HIGH RISK",
                          VerificationSession.risk_score >= settings.RISK_THRESHOLD_HIGH)).count()

    # Average verification time placeholder (we do not track durative metrics in
    # this prototype; derive a heuristic for the demo dashboard).
    avg_time_seconds = 12 if total else 0

    return {
        "total_verifications": total,
        "verified": verified,
        "review_required": review,
        "high_risk": high,
        "fraud_detected": fraud,
        "average_verification_time_seconds": avg_time_seconds,
    }
