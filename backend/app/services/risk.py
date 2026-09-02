"""Explainable risk scoring engine.

Turns a set of verification signals into a 0-100 risk score with a readable
explanation of *why* the score is what it is.  Weights are configurable via
``app.config.Settings.RISK_WEIGHTS``.

Decision bands (configurable):
    LOW    : 0  - 30    -> VERIFIED
    MEDIUM : 31 - 60    -> REVIEW REQUIRED
    HIGH   : 61 - 100   -> HIGH RISK
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..config import settings


@dataclass
class RiskContribution:
    signal: str
    weight: int
    applied: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "signal": self.signal,
            "weight": self.weight,
            "applied": self.applied,
            "reason": self.reason,
        }


@dataclass
class RiskResult:
    score: int
    level: str                # LOW | MEDIUM | HIGH
    decision: str             # VERIFIED | REVIEW REQUIRED | HIGH RISK
    contributions: list = field(default_factory=list)
    reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "level": self.level,
            "decision": self.decision,
            "contributions": [c.to_dict() for c in self.contributions],
            "reasons": self.reasons,
        }


# Each entry: (signal_key, active_bool, reason_if_active)
def score(active_signals: dict) -> RiskResult:
    """Compute the risk score from a dict of active signals.

    ``active_signals`` keys map to ``RISK_WEIGHTS`` keys (a subset).  Truthy
    values enable the contribution; a value of False/None/0 disables it.
    """
    weights = getattr(settings, "RISK_WEIGHTS", {})
    contributions: list = []
    reasons: list = []
    total = 0

    for signal, weight in weights.items():
        active = bool(active_signals.get(signal))
        reason = ""
        if signal == "invalid_mrz":
            reason = "MRZ zone failed checksum / could not be validated."
        elif signal == "ocr_mrz_mismatch":
            reason = "OCR-extracted data conflicts with the MRZ zone."
        elif signal == "expired_passport":
            reason = "Passport is past its expiry date."
        elif signal == "expiring_passport":
            reason = "Passport expires within the expiring-soon window."
        elif signal == "expired_visa":
            reason = "Visa is past its expiry date."
        elif signal == "face_mismatch":
            reason = "Face match below the acceptance threshold."
        elif signal == "face_low_quality":
            reason = "Face image could not be verified / too low quality."
        elif signal == "watchlist_match":
            reason = "Document / identity matched the (demo) watchlist."
        elif signal == "tamper_high":
            reason = "Strong document tampering indicators detected."
        elif signal == "tamper_medium":
            reason = "Moderate document anomaly indicators detected."
        elif signal == "duplicate_identity":
            reason = "Possible duplicate / multiple identity found."
        elif signal == "blacklist":
            reason = "Document found on the (demo) blacklist."
        elif signal == "document_type_suspect":
            reason = "Document type / format is inconsistent or suspect."
        elif signal == "passport_not_found":
            reason = "Document number was not found in the reference database."
        elif signal == "document_anomaly":
            reason = "Document status / record flag indicates an anomaly."

        if active:
            contributions.append(RiskContribution(signal, weight, True, reason))
            reasons.append(f"{signal.replace('_', ' ').title()}: +{weight} - {reason}")
            total += weight
        else:
            contributions.append(RiskContribution(signal, weight, False, ""))

    # Clamp
    score_val = max(0, min(100, total))

    low_th = getattr(settings, "RISK_THRESHOLD_MEDIUM", 30)
    high_th = getattr(settings, "RISK_THRESHOLD_HIGH", 61)

    if score_val >= high_th:
        level, decision = "HIGH", "HIGH RISK"
    elif score_val >= low_th:
        level, decision = "MEDIUM", "REVIEW REQUIRED"
    else:
        level, decision = "LOW", "VERIFIED"

    # Add a baseline "everything else OK" reason only if nothing active
    if not any(c.applied for c in contributions):
        reasons.append("No significant negative signals detected.")

    return RiskResult(score=score_val, level=level, decision=decision,
                      contributions=contributions, reasons=reasons)


def map_decision(level: str) -> str:
    return {"LOW": "VERIFIED", "MEDIUM": "REVIEW REQUIRED",
            "HIGH": "HIGH RISK"}.get(level, "REVIEW REQUIRED")
