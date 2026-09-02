"""Machine Readable Zone (MRZ) parser and validator.

Implements ICAO Document 9303 parsing for the three standard MRZ formats:

* ``TD3``  - Passport: 2 lines of 44 characters (``P<``)
* ``TD1``  - ID card / small document: 3 lines of 30 characters
* ``TD2``  - Visa / larger ID card: 2 lines of 36 characters

Each parser validates the check digits using the ICAO ``7, 3, 1`` weighted
mod-10 algorithm.  The module is dependency free so it can be unit tested in
isolation and used offline at a border checkpoint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Check digit computation
# ---------------------------------------------------------------------------

# Values: 0-9 -> 0-9, A-Z -> 10-35, '<' -> 0. Case is normalised.
def _char_value(ch: str) -> int:
    ch = ch.upper()
    if "0" <= ch <= "9":
        return int(ch)
    if "A" <= ch <= "Z":
        return ord(ch) - ord("A") + 10
    # '<', '+', space, anything unknown
    return 0


_WEIGHTS = (7, 3, 1)


def compute_check_digit(text: str) -> int:
    """Return the ICAO check digit (0-9) for a field string."""
    if not text:
        raise ValueError("Cannot compute check digit for empty field")
    total = 0
    for i, ch in enumerate(text):
        total += _char_value(ch) * _WEIGHTS[i % 3]
    return total % 10


def is_valid_check_digit(field: str, check: str) -> bool:
    """Verify that the check digit string (single char) matches the field."""
    expected = compute_check_digit(field)
    return _char_value(check) == expected


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MRZField:
    name: str
    value: str = ""
    verified: Optional[bool] = None  # None = no check digit present


@dataclass
class MRZResult:
    document_type: str = ""           # e.g. "P" (passport), "I" (ID), "V" (visa)
    issuing_country: str = ""         # 3-letter ICAO code
    surname: str = ""
    given_names: str = ""
    document_number: str = ""
    nationality: str = ""
    date_of_birth: str = ""           # YYMMDD
    sex: str = ""
    date_of_expiry: str = ""          # YYMMDD
    personal_number: str = ""
    optional_data: str = ""
    format: str = ""                  # TD1 / TD2 / TD3
    raw_lines: list = field(default_factory=list)
    checks: list = field(default_factory=list)      # list of {field, ok, expected, got}
    checksum_passed: bool = False
    composite_checksum_passed: bool = False
    errors: list = field(default_factory=list)

    # Convenience parsed dates
    @property
    def dob(self) -> Optional[datetime]:
        return _parse_yyyymmdd(self.date_of_birth)

    @property
    def expiry(self) -> Optional[datetime]:
        return _parse_yyyymmdd(self.date_of_expiry)

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.surname, self.given_names) if p)

    def as_dict(self) -> dict:
        return {
            "format": self.format,
            "document_type": self.document_type,
            "issuing_country": self.issuing_country,
            "surname": self.surname,
            "given_names": self.given_names,
            "full_name": self.full_name,
            "document_number": self.document_number,
            "nationality": self.nationality,
            "date_of_birth": self.date_of_birth,
            "dob_iso": self.dob.isoformat() if self.dob else None,
            "sex": self.sex,
            "date_of_expiry": self.date_of_expiry,
            "expiry_iso": self.expiry.isoformat() if self.expiry else None,
            "personal_number": self.personal_number,
            "optional_data": self.optional_data,
            "checksum_passed": self.checksum_passed,
            "composite_checksum_passed": self.composite_checksum_passed,
            "checks": self.checks,
            "errors": self.errors,
            "raw_lines": self.raw_lines,
        }


def _parse_yyyymmdd(value: str) -> Optional[datetime]:
    """Parse YYMMDD -> datetime. Handles 30/50 year pivot (ICAO)."""
    if not value or len(value) != 6 or not value.isdigit():
        return None
    yy = int(value[0:2])
    year = 2000 + yy if yy < 50 else 1900 + yy
    try:
        return datetime(year, int(value[2:4]), int(value[4:6]))
    except ValueError:
        return None


def _clean(text: str) -> str:
    """Normalise a line: strip whitespace, pad/truncate to width with '<'."""
    text = text.rstrip("\r\n")
    return text.replace(" ", "<").upper()


def _split_name(field: str) -> tuple[str, str]:
    """Split a name field on '<<' separators into surname and given names."""
    parts = [p.replace("<", " ").strip() for p in field.split("<<")]
    surname = parts[0] if parts else ""
    given = parts[1] if len(parts) > 1 else ""
    return surname, given


# ---------------------------------------------------------------------------
# TD3 - Passport (2 x 44)
# ---------------------------------------------------------------------------

def _parse_td3(lines: list[str]) -> MRZResult:
    res = MRZResult(format="TD3")
    l1, l2 = lines[0], lines[1]

    res.document_type = l1[0]
    res.issuing_country = l1[2:5] if len(l1) >= 5 else ""
    res.surname, res.given_names = _split_name(l1[5:44])

    res.document_number = l2[0:9]
    res.nationality = l2[10:13]
    res.date_of_birth = l2[13:19]
    res.sex = l2[20] if len(l2) > 20 else ""
    res.date_of_expiry = l2[21:27]
    res.personal_number = l2[28:43]
    res.raw_lines = lines

    # Checks
    res.checks = []

    def ck(field, digit, label):
        ok = False
        if digit and digit in "<0123456789":
            try:
                ok = is_valid_check_digit(field, digit)
            except ValueError:
                ok = False
        res.checks.append({
            "field": label, "ok": ok,
            "expected": compute_check_digit(field) if field else None,
            "got": digit,
        })
        return ok

    doc_ok = ck(res.document_number, l2[9], "document_number")
    dob_ok = ck(res.date_of_birth, l2[19], "date_of_birth")
    exp_ok = ck(res.date_of_expiry, l2[27], "date_of_expiry")
    per_ok = ck(res.personal_number, l2[42], "personal_number")

    res.checksum_passed = all(c["ok"] for c in res.checks)

    # Composite check digit over raw line (all fields + check digits)
    composite = ""
    if len(l2) >= 43:
        composite = compute_check_digit(l2[:43]) if l2[:43] else -1
        got = _char_value(l2[43])
        res.composite_checksum_passed = got == composite
    res.errors = [c["field"] for c in res.checks if not c["ok"]]
    res.checksum_passed = res.checksum_passed and res.composite_checksum_passed
    return res


# ---------------------------------------------------------------------------
# TD1 - ID / small doc (3 x 30)
# ---------------------------------------------------------------------------

def _parse_td1(lines: list[str]) -> MRZResult:
    res = MRZResult(format="TD1")
    l1, l2, l3 = lines[0], lines[1], lines[2]

    res.document_type = l1[0]
    res.issuing_country = l1[2:5]
    res.document_number = l1[5:14]
    res.optional_data = l1[15:30]

    res.date_of_birth = l2[0:6]
    res.sex = l2[7] if len(l2) > 7 else ""
    res.date_of_expiry = l2[8:14]
    res.nationality = l2[15:18]

    res.surname, res.given_names = _split_name(l3[0:30])
    res.raw_lines = lines

    res.checks = []

    def ck(field, digit, label):
        ok = False
        if digit and digit in "<0123456789":
            try:
                ok = is_valid_check_digit(field, digit)
            except ValueError:
                ok = False
        res.checks.append({
            "field": label, "ok": ok,
            "expected": compute_check_digit(field) if field else None,
            "got": digit,
        })
        return ok

    ck(res.document_number, l1[14], "document_number")
    ck(res.date_of_birth, l2[6], "date_of_birth")
    ck(res.date_of_expiry, l2[14], "date_of_expiry")

    res.checksum_passed = all(c["ok"] for c in res.checks)
    res.errors = [c["field"] for c in res.checks if not c["ok"]]
    return res


# ---------------------------------------------------------------------------
# TD2 - Visa / larger doc (2 x 36)
# ---------------------------------------------------------------------------

def _parse_td2(lines: list[str]) -> MRZResult:
    res = MRZResult(format="TD2")
    l1, l2 = lines[0], lines[1]

    res.document_type = l1[0]
    res.issuing_country = l1[2:5]
    res.document_number = l1[5:9]
    res.surname, res.given_names = _split_name(l1[10:36])

    res.nationality = l2[3:6] if len(l2) > 6 else ""
    res.date_of_birth = l2[6:12]
    res.sex = l2[13] if len(l2) > 13 else ""
    res.date_of_expiry = l2[14:20]
    res.optional_data = l2[21:36]
    res.raw_lines = lines

    res.checks = []

    def ck(field, digit, label):
        ok = False
        if digit and digit in "<0123456789":
            try:
                ok = is_valid_check_digit(field, digit)
            except ValueError:
                ok = False
        res.checks.append({
            "field": label, "ok": ok,
            "expected": compute_check_digit(field) if field else None,
            "got": digit,
        })
        return ok

    ck(res.document_number, l1[9], "document_number")
    ck(res.date_of_birth, l2[12], "date_of_birth")
    ck(res.date_of_expiry, l2[20], "date_of_expiry")

    res.checksum_passed = all(c["ok"] for c in res.checks)
    res.errors = [c["field"] for c in res.checks if not c["ok"]]
    return res


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_MRZ_LINE_RE = re.compile(r"^[A-Z0-9<]{3,}\s*$")


def _detect_format(lines: list[str]) -> Optional[str]:
    """Detect the MRZ format from the line widths."""
    for line in lines:
        if len(line) != len(lines[0]):
            return None
    width = len(lines[0])
    if width == 44 and len(lines) == 2:
        return "TD3"
    if width == 30 and len(lines) == 3:
        return "TD1"
    if width == 36 and len(lines) == 2:
        return "TD2"
    return None


def parse_mrz(lines: list[str]) -> Optional[MRZResult]:
    """Parse raw MRZ lines into an MRZResult.

    Returns ``None`` if the lines do not look like a valid MRZ block.
    """
    if not lines:
        return None
    cleaned = [_clean(l) for l in lines if l and _clean(l)]
    if len(cleaned) < 2:
        return None

    fmt = _detect_format(cleaned)
    if fmt == "TD3" and len(cleaned) >= 2:
        return _parse_td3(cleaned[:2])
    if fmt == "TD1" and len(cleaned) >= 3:
        return _parse_td1(cleaned[:3])
    if fmt == "TD2" and len(cleaned) >= 2:
        return _parse_td2(cleaned[:2])

    # Fallback: try TD3 layout with 2 lines regardless of strict width
    if len(cleaned) == 2 and all(len(l) <= 44 for l in cleaned):
        # Only treat as TD3 if first char is a document-type letter and it
        # contains typical separator structure.
        if cleaned[0][0] in "PIV":
            return _parse_td3(cleaned)
    return None


def extract_mrz_from_text(text: str) -> Optional[MRZResult]:
    """Find the MRZ region inside raw OCR text and parse it.

    Searches for 2-3 consecutive lines whose characters are all in the
    MRZ alphabet (letters / digits / '<').
    """
    lines = [ln.rstrip() for ln in text.splitlines()]
    blocked = [ln for ln in lines if len(ln.strip()) >= 3]
    if not blocked:
        return None

    # Find candidate windows of 2/3 consecutive MRZ-like lines
    def is_mrz_line(ln):
        return bool(_MRZ_LINE_RE.match(ln.strip())) and len(ln.strip()) >= 20

    result = None
    best = -1
    n = len(blocked)
    for window in (3, 2):
        for i in range(n - window + 1):
            group = blocked[i:i + window]
            if all(is_mrz_line(ln) for ln in group):
                parsed = parse_mrz(group)
                if parsed:
                    score = parsed.checksum_passed * 2 + len(group)
                    if score > best:
                        best = score
                        result = parsed
    return result
