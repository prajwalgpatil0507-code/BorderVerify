import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # backend on path

from app.services.orchestrator import verify_image, verify_demo
from app.schemas.schemas import RawVerifyRequest

def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + '\n'); sys.stdout.flush()

log("=== VALID PASSPORT (image pipeline) ===")
res = verify_image(os.path.join('data', 'samples', 'valid_passport.png'))
log("DOC TYPE:", res['document_type'])
log("OCR TEXT:\n" + res['ocr']['text'])
mrz = res['mrz']
log("MRZ docnum:", mrz['document_number'] if mrz else None, "checksum_ok:", res['mrz_checksum_valid'])
log("PASSENGER:", res['passenger'])
log("CROSSCHECK consistent:", res['cross_check']['overall_consistent'], "mismatches:", res['cross_check']['mismatch_count'])
log("RISK score:", res['risk']['score'], "decision:", res['risk']['decision'])
log("EXPIRY:", res['expiry']['status'])

log("")
log("=== EXPIRED PASSPORT ===")
res = verify_image(os.path.join('data', 'samples', 'expired_passport.png'))
log("RISK:", res['risk']['score'], res['risk']['decision'], "expiry:", res['expiry']['status'])

log("")
log("=== MISMATCH (tampered) PASSPORT ===")
res = verify_image(os.path.join('data', 'samples', 'mismatch_passport.png'))
log("MRZ docnum:", res['mrz']['document_number'] if res['mrz'] else None,
    "OCR reads P12345678", "checksum_ok:", res['mrz_checksum_valid'])
log("CROSSCHECK consistent:", res['cross_check']['overall_consistent'], "mismatches:", res['cross_check']['mismatch_count'])
log("RISK:", res['risk']['score'], res['risk']['decision'])

log("")
log("=== WATCHLIST PASSPORT ===")
res = verify_image(os.path.join('data', 'samples', 'watchlist_passport.png'))
log("watchlist matched:", res['watchlist']['matched'], "RISK:", res['risk']['score'], res['risk']['decision'])

log("")
log("=== DEMO SCENARIOS ===")
for sc in ['valid', 'expired', 'mrz_mismatch', 'face_mismatch', 'tamper', 'watchlist', 'duplicate']:
    r = verify_demo(RawVerifyRequest(scenario=sc))
    log(f"{sc:15s} -> score={r['risk']['score']:<3} level={r['risk']['level']:<6} decision={r['risk']['decision']}")

log("")
log("ALL INTEGRATION TESTS COMPLETE")
