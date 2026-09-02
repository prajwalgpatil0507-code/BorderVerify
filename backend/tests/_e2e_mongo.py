"""End-to-end: login -> upload -> verify/document + demo scenarios (MongoDB)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLES = os.path.join(ROOT, "data", "samples")


def auth():
    r = client.post("/api/auth/login",
                    data={"username": "officer", "password": "SIH@2026Demo"})
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def main():
    h = auth()
    print("login OK")

    # --- Demo scenario: valid -> VERIFIED (Mongo lookup) ---
    r = client.post("/api/verify/demo", json={"scenario": "valid"}, headers=h)
    v = r.json()
    print("\n[valid] decision:", v["risk"]["decision"], "| score:", v["risk"]["score"],
          "| backend:", v.get("backend"),
          "| passport_found:", v["passport"]["found"])
    assert v["risk"]["decision"] == "VERIFIED", "valid scenario should VERIFY"
    assert v.get("backend") == "mongodb", "should use mongodb backend"
    assert v["passport"]["found"] is True, "valid doc should be found in Mongo"

    # --- Demo scenario: not_found -> passport_not_found signal ---
    r = client.post("/api/verify/demo", json={"scenario": "not_found"}, headers=h)
    v = r.json()
    sigs = [c["signal"] for c in v["risk"]["contributions"] if c["applied"]]
    print("\n[not_found] decision:", v["risk"]["decision"], "| score:", v["risk"]["score"],
          "| signals:", sigs)
    assert "passport_not_found" in sigs, "not_found should raise passport_not_found"

    # --- Upload + verify the valid sample image ---
    doc_path = os.path.join(SAMPLES, "valid_passport.png")
    with open(doc_path, "rb") as fh:
        up = client.post("/api/upload-document",
                         files={"file": ("valid_passport.png", fh, "image/png")})
    print("\n[upload] status:", up.status_code, up.json())
    fn = up.json()["filename"]
    r = client.post("/api/verify/document",
                    json={"image_filename": fn, "document_type": "auto"},
                    headers=h)
    v = r.json()
    print("\n[image verify] doc_no:", v["passenger"].get("document_number"),
          "| decision:", v["risk"]["decision"], "| score:", v["risk"]["score"],
          "| backend:", v.get("backend"), "| passport_found:", v["passport"]["found"])
    print("  violations:", v["cross_check"].get("overall_consistent"))
    print("  mrz_checksum:", v.get("mrz_checksum_valid"))

    # --- Demo database endpoints spot-check ---
    r = client.get("/api/database/overview", headers=h)
    print("\n[database overview] storage:", r.json()["storage"],
          "| counts:", r.json()["counts"])

    print("\nALL E2E ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
