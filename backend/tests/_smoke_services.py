import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # backend dir on path
import numpy as np, cv2

print("Importing services...")
from app.services import mrz, date_utils, countries, ocr, crosscheck, tamper, face, watchlist, dedupe, risk
print("All service imports OK")

# countys
print("country_name UTO ->", countries.country_name("UTO"))

# date expiry
from datetime import date, timedelta
from app.services.date_utils import expiry_status
print("expired:", expiry_status(date(2020,1,1))["status"])
print("expiring_soon:", expiry_status(date(2036,1,1), 180)["status"])
print("valid:", expiry_status(date(2040,1,1), 180)["status"])

# risk
from app.services.risk import score
r = score({"face_mismatch": True, "expired_passport": True, "ocr_mrz_mismatch": True})
print("risk score:", r.score, "level:", r.level, "decision:", r.decision)
print("reasons:", r.reasons)

# crosscheck quickly
from app.services.crosscheck import validate
mrz_res = mrz.parse_mrz([
    "P<UTORAIJILO<<MARK<THOMAS" + "<"*30,
    "P123456789UTO0005049M25091270<<<<<<<<<<<<<07"
])
ocr_f = {"passport_number": {"value": "P12345678"}, "date_of_birth": {"value": "000504"},
         "surname": {"value": "RAIJILO"}, "given_names": {"value": "MARK THOMAS"},
         "nationality": {"value": "UTO"}, "date_of_expiry": {"value": "250912"}, "sex": {"value": "M"}}
cv = validate(ocr_f, mrz_res)
print("crossvalidate overall:", cv.overall_consistent, "mismatches:", cv.mismatch_count)

# watchlist
from app.services.watchlist import check_watchlist
print("watchlist clear:", check_watchlist("P12345678").matched)
print("watchlist hit:", check_watchlist("X99887766").matched, check_watchlist("X99887766").reason)

# dedupe
from app.services.dedupe import check_duplicates
dup = check_duplicates({"surname":"RAIJILO","given_names":"MARK THOMAS","date_of_birth":"000504","nationality":"UTO"}, face_score=0.9)
print("duplicate:", dup.is_duplicate, dup.confidence)

print("ALL SERVICE SMOKE TESTS PASSED")
