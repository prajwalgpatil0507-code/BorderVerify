import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app')))
from services.mrz import (
    compute_check_digit, is_valid_check_digit, parse_mrz, extract_mrz_from_text,
)
from services.mrz import _clean

# --- Unit: check digit algorithm (hand-verified) ---
assert compute_check_digit("P1234567") == 1, compute_check_digit("P1234567")
assert compute_check_digit("000504") == 9
assert compute_check_digit("250912") == 7
assert is_valid_check_digit("P1234567", "1") is True
assert is_valid_check_digit("P1234567", "2") is False

# --- Build a valid TD3 passport (9-char doc number P12345678) ---
doc_no = "P12345678"
doc_check = str(compute_check_digit(doc_no))
dob = "000504"
dob_check = str(compute_check_digit(dob))
expiry = "250912"
exp_check = str(compute_check_digit(expiry))
personal = "0" + "<" * 13   # 14-char personal number field
personal_check = str(compute_check_digit(personal))

core = doc_no + doc_check + "UTO" + dob + dob_check + "M" + expiry + exp_check + personal + personal_check
assert len(core) == 43, len(core)
comp = str(compute_check_digit(core))
line2 = _clean(core + comp)[:44]

line1 = _clean("P<UTORAIJILO<<MARK<THOMAS" + "<" * 30)[:44]
print("L1:", repr(line1), len(line1))
print("L2:", repr(line2), len(line2))
assert len(line1) == 44 and len(line2) == 44

res = parse_mrz([line1, line2])
print("format:", res.format)
print("type:", res.document_type, "country:", res.issuing_country)
print("name:", res.full_name)
print("docnum:", res.document_number, "nat:", res.nationality, "sex:", res.sex)
print("dob:", res.date_of_birth, "expiry:", res.date_of_expiry)
print("checksum_passed:", res.checksum_passed, "composite:", res.composite_checksum_passed)
print("checks:", res.checks)
print("errors:", res.errors)

assert res.document_type == "P"
assert res.issuing_country == "UTO"
assert res.surname == "RAIJILO"
assert res.given_names == "MARK THOMAS"
assert res.document_number == "P12345678"
assert res.nationality == "UTO"
assert res.date_of_birth == "000504"
assert res.date_of_expiry == "250912"
assert res.sex == "M"
assert res.checksum_passed is True
assert res.composite_checksum_passed is True

# --- Tampered MRZ: flip a digit in doc number so checksum fails ---
bad = line2[:8] + ("9" if line2[8] != "9" else "8") + line2[9:44]
res2 = parse_mrz([line1, bad])
print("tampered checksum_passed:", res2.checksum_passed, "errors:", res2.errors)
assert res2.checksum_passed is False

# --- extract_mrz_from_text on raw OCR text ---
raw_text = "REPUBLIC OF UTOPIA\nPASSPORT\nSurname RAIJILO  Name MARK THOMAS\n" + line1 + "\n" + line2
res3 = extract_mrz_from_text(raw_text)
print("extracted:", res3.document_number if res3 else None)
assert res3 is not None and res3.document_number == "P12345678"

# --- invalid input returns None ---
assert parse_mrz([]) is None
assert extract_mrz_from_text("hello world no mrz here") is None

print("ALL MRZ TESTS PASSED")
