"""Cross-validation of OCR-extracted data against the (authoritative) MRZ zone."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FieldCheck:
    field: str
    ocr_value: str
    mrz_value: str
    consistent: bool
    status: str      # "match" | "mismatch" | "unavailable"
    explanation: str

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "ocr_value": self.ocr_value,
            "mrz_value": self.mrz_value,
            "consistent": self.consistent,
            "status": self.status,
            "explanation": self.explanation,
        }


@dataclass
class CrossValidationResult:
    checks: list = field(default_factory=list)
    overall_consistent: bool = True
    mismatch_count: int = 0
    mismatches: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "overall_consistent": self.overall_consistent,
            "mismatch_count": self.mismatch_count,
            "mismatches": self.mismatches,
        }


def _norm(value: str) -> str:
    """Normalisation: uppercase, drop spaces, punctuation and filler chars."""
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _name_normalise(value: str) -> str:
    """Normalise a personal name for comparison (drop space separators)."""
    return _norm(value)


def _date_normalise(value: str) -> str:
    """Normalise date strings from various formats to YYMMDD-like digits."""
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits


def compare_field(field: str, ocr_value: str, mrz_value: str,
                  kind: str = "exact") -> FieldCheck:
    """Compare one OCR value against the corresponding MRZ value."""
    a = _norm(ocr_value)
    b = _norm(mrz_value)

    if not a and not b:
        return FieldCheck(field, ocr_value or "", mrz_value or "", True,
                          "unavailable",
                          "Neither OCR nor MRZ provided a value for this field.")

    # A value is only present on one side -> not proof of tampering; flag the
    # field as unavailable for comparison rather than as a hard mismatch.
    if a and not b:
        return FieldCheck(field, ocr_value or "", mrz_value or "", True,
                          "unavailable",
                          f"OCR read '{ocr_value}' but the MRZ did not supply an "
                          f"equivalent field for comparison.")

    if b and not a:
        return FieldCheck(field, ocr_value or "", mrz_value, True,
                          "unavailable",
                          f"MRZ states '{mrz_value}' but OCR could not read this "
                          f"field for comparison.")

    # Both present. Compare based on kind.
    if kind == "date":
        match = _date_normalise(a) == _date_normalise(b)
    elif kind == "name":
        match = _name_normalise(a) == _name_normalise(b)
    else:
        match = a == b

    status = "match" if match else "mismatch"
    return FieldCheck(field, ocr_value, mrz_value, match, status,
                      "Values agree." if match else
                      f"'{ocr_value}' (OCR) does not match MRZ value '{mrz_value}'.")


def validate(ocr_fields: dict, mrz: Optional[object]) -> CrossValidationResult:
    """Compare a dict of OCR fields against a parsed MRZResult.

    ``ocr_fields`` keys are expected using the *_value keys emitted by the OCR
    field extractor (e.g. ``passport_number``).  Only fields that the MRZ
    provides are checked.
    """
    res = CrossValidationResult()
    if mrz is None:
        res.overall_consistent = False
        res.mismatch_count = 1
        res.mismatches.append("No MRZ zone found - cannot cross-validate.")
        return res

    def ocr(key):
        v = ocr_fields.get(key)
        if isinstance(v, dict):
            return v.get("value")
        return v

    # Passport number
    res.checks.append(compare_field("document_number", ocr("passport_number"),
                                    mrz.document_number, "exact"))
    # Date of birth
    res.checks.append(compare_field("date_of_birth", ocr("date_of_birth"),
                                    mrz.date_of_birth, "date"))
    # Surname / given names (compare combined name)
    mrz_name = (mrz.surname + mrz.given_names).strip()
    ocr_name = (ocr("surname") or "") + (ocr("given_names") or "")
    if not ocr_name:
        ocr_name = ocr("name") or ocr("full_name") or ""
    res.checks.append(compare_field("name", ocr_name, mrz_name, "name"))

    # Nationality
    res.checks.append(compare_field("nationality", ocr("nationality"),
                                    mrz.nationality, "exact"))
    # Expiry
    res.checks.append(compare_field("date_of_expiry", ocr("date_of_expiry"),
                                    mrz.date_of_expiry, "date"))
    # Sex
    res.checks.append(compare_field("sex", ocr("sex"), mrz.sex, "exact"))

    for c in res.checks:
        if c.status == "mismatch":
            res.overall_consistent = False
            res.mismatch_count += 1
            res.mismatches.append(c.explanation)

    return res
