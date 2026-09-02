import sys, os, cv2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.ocr import run_ocr, extract_fields
from app.services.mrz import extract_mrz_from_text
from app.services import crosscheck

p = os.path.join('data', 'samples', 'valid_passport.png')
img = cv2.imread(p, cv2.IMREAD_COLOR)
res = run_ocr(img)
print("=== TEXT ===")
print(res.text)
print("=== FIELDS ===")
fields = extract_fields(res.text)
for k, v in fields.items():
    print(f"  {k} = {v['value']!r}")
print("=== MRZ ===")
mrz = extract_mrz_from_text(res.text)
print("docnum", mrz.document_number, "country", mrz.issuing_country, "dob", mrz.date_of_birth,
      "exp", mrz.date_of_expiry, "sex", mrz.sex, "nat", mrz.nationality,
      "surname", mrz.surname, "given", mrz.given_names)
print("=== CROSSCHECK ===")
cv = crosscheck.validate(fields, mrz)
for c in cv.checks:
    print(f"  {c.field:16s} ocr={c.ocr_value!r} mrz={c.mrz_value!r} consistent={c.consistent} status={c.status}")
print("overall_consistent", cv.overall_consistent, "mismatches", cv.mismatch_count)
