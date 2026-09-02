"""Duplicate / multiple-identity detection for the prototype.

Compares the candidate's attributes against synthetic "prior" records and a
running store of previously-verified passengers.  Commercial-grade dedup would
use fuzzy string matching + face embeddings over a large population; this is a
transparent, rule-based prototype that can be extended.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from difflib import SequenceMatcher

from .watchlist import get_demo_existing_records


@dataclass
class DuplicateSignal:
    field: str
    similarity: float          # 0..1
    description: str

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "similarity": round(self.similarity, 3),
            "description": self.description,
        }


@dataclass
class DuplicateResult:
    is_duplicate: bool
    confidence: float          # 0..1
    signals: list = field(default_factory=list)
    matched_record: Optional[dict] = None
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "is_duplicate": self.is_duplicate,
            "confidence": round(self.confidence, 3),
            "signals": [s.to_dict() for s in self.signals],
            "matched_record": self.matched_record,
            "explanation": self.explanation,
        }


def _name_similarity(a: str, b: str) -> float:
    a = "".join(ch for ch in (a or "").upper() if ch.isalnum())
    b = "".join(ch for ch in (b or "").upper() if ch.isalnum())
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _norm_dob(s: str) -> str:
    """Normalise a date to YYYYMMDD so ISO (1995-09-14) and MRZ (950914) compare."""
    d = "".join(ch for ch in (s or "") if ch.isdigit())
    if len(d) == 6:                      # YYMMDD
        yy = int(d[:2])
        return ("19" if yy >= 50 else "20") + d
    if len(d) == 8 and d[0] == "0":      # DDMMYYYY
        return d[4:8] + d[2:4] + d[0:2]
    return d if len(d) == 8 else ""      # assume YYYYMMDD


def _dob_similarity(a: str, b: str) -> float:
    a = _norm_dob(a)
    b = _norm_dob(b)
    if not a or not b:
        return 0.0
    return 1.0 if a == b else 0.0


def _find_matches(attrs: dict, face_score: Optional[float],
                  prior_records: Optional[list[dict]] = None) -> DuplicateResult:
    """Search for a potential duplicate among ``prior_records``.

    ``attrs`` is a dict with optional keys: surname, given_names, date_of_birth,
    nationality, document_number, face_score (0..1).
    """
    records = prior_records if prior_records is not None else get_demo_existing_records()
    best_confidence = 0.0
    best = None
    best_signals = []

    face_score = attrs.get("face_score", face_score)

    for rec in records:
        sigs = []
        name_sim = _name_similarity(
            (attrs.get("surname", "") + attrs.get("given_names", "")),
            (rec.get("surname", "") + rec.get("given_names", "")))
        if name_sim > 0.4:
            sigs.append(DuplicateSignal("name", name_sim,
                                        f"Name similarity {int(name_sim * 100)}%"))

        dob_sim = _dob_similarity(attrs.get("date_of_birth", ""),
                                  rec.get("date_of_birth", ""))
        if dob_sim > 0.0:
            sigs.append(DuplicateSignal("date_of_birth", dob_sim,
                                        "Date of birth matches."))

        doc_dup = False
        if attrs.get("document_number"):
            doc_dup = attrs["document_number"].upper() == rec.get("document_number", "").upper()
        if doc_dup:
            sigs.append(DuplicateSignal("document_number", 1.0,
                                        "Document number matches a prior record."))

        # Face similarity, if provided
        if face_score is not None and face_score >= 0.6:
            sigs.append(DuplicateSignal("face", face_score,
                                        f"Face similarity {int(face_score * 100)}%"))

        if not sigs:
            continue

        # Weighted confidence
        conf = 0.0
        weights = {"name": 0.3, "date_of_birth": 0.25, "document_number": 0.35,
                   "face": 0.35}
        total_w = 0.0
        for s in sigs:
            w = weights.get(s.field, 0.2)
            conf += s.similarity * w
            total_w += w
        conf = conf / total_w if total_w else 0.0

        if conf > best_confidence:
            best_confidence = conf
            best = rec
            best_signals = sigs

    if best is not None and best_confidence >= 0.55:
        is_dup = best_confidence >= 0.7
        if not is_dup and any(s.field in ("face", "document_number") and s.similarity >= 0.9
                              for s in best_signals):
            is_dup = True
        return DuplicateResult(
            is_duplicate=is_dup, confidence=best_confidence,
            signals=best_signals, matched_record=best,
            explanation=("Potential duplicate identity with a prior record."
                         if is_dup else
                         "Partial match with a prior record - manual review advised."))
    return DuplicateResult(is_duplicate=False, confidence=best_confidence,
                           signals=best_signals)


def check_duplicates(attrs: dict, face_score: Optional[float] = None,
                     prior_records: Optional[list[dict]] = None) -> DuplicateResult:
    return _find_matches(attrs, face_score, prior_records)
