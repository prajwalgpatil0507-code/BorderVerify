"""Validate that MongoDB look-ups drive the correct risk decision per scenario."""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import orchestrator as orch
from app.services import providers as p


def summarize(label, result):
    risk = result["risk"]
    passport = result["passport"]
    watchlist = result["watchlist"]
    print(f"\n=== {label} ===")
    print("  passport found :", passport["found"],
          "| status:", passport.get("status"), "| anomaly:", passport.get("anomaly"))
    print("  watchlist match:", watchlist["matched"], "-", watchlist.get("category"))
    print("  level:", risk["level"], "| decision:", risk["decision"], "| score:", risk["score"])
    contribs = [c["signal"] for c in risk["contributions"] if c["applied"]]
    print("  signals:", contribs)
    print("  backend:", result.get("backend"))
    return risk


def main():
    print("backend:", p.backend_kind())

    # Fake request objects (Plain namespace is enough for verify_demo).
    def req(**kw):
        from types import SimpleNamespace
        d = {"scenario": None, "document_number": None, "surname": None,
             "given_names": None, "date_of_birth": None, "nationality": None,
             "sex": None, "date_of_expiry": None, "face_score": None,
             "mrz_lines": None, "document_type": None}
        d.update(kw)
        return SimpleNamespace(**d)

    scenarios = [
        ("valid", req(scenario="valid"), "LOW/VERIFIED"),
        ("not found", req(scenario="valid", document_number="PX0000000"), "passport_not_found (+20)"),
        ("expired passport", req(scenario="expired"), "expired_passport (+30)"),
        ("expired visa", req(scenario="valid", document_number="P2345678"), "expired_visa (+30)"),
        ("watchlist", req(scenario="watchlist"), "watchlist_match (+65)"),
        ("mrz mismatch", req(scenario="mrz_mismatch"), "ocr_mrz_mismatch (+40)"),
        ("duplicate", req(scenario="duplicate"), "duplicate_identity (+40)"),
    ]
    for label, r, expect in scenarios:
        result = orch.verify_demo(r)
        risk = summarize(label, result)
        print("  expected:", expect, "-> OK" if risk["score"] > 0 or expect == "LOW/VERIFIED" else "")

    # Real image path (valid_passport.png -> P1234567)
    img = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "data", "samples", "valid_passport.png")
    if os.path.exists(img):
        result = orch.verify_image(img)
        print("\n=== verify_image(valid_passport.png) ===")
        print("  doc_no:", result["passenger"].get("document_number"))
        print("  passport found:", result["passport"]["found"],
              "| status:", result["passport"].get("status"))
        risk = result["risk"]
        print("  level:", risk["level"], "| decision:", risk["decision"], "| score:", risk["score"])
        contribs = [c["signal"] for c in risk["contributions"] if c["applied"]]
        print("  signals:", contribs)
    else:
        print("\n(valid_passport.png not found:", img, ")")
    print("\nDONE")


if __name__ == "__main__":
    main()
