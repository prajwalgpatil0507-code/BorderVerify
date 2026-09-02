import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from starlette.testclient import TestClient
from app.main import app

c = TestClient(app)

r = c.post("/api/auth/login", data={"username": "officer", "password": "SIH@2026Demo"})
assert r.status_code == 200, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}

for sid, expect in [
    ("aadhaar_valid", ("LOW", "VERIFIED", 0)),
    ("aadhaar_tampered", ("HIGH", "HIGH RISK", 70)),
    ("pan_valid", ("LOW", "VERIFIED", 0)),
    ("pan_tampered", ("HIGH", "HIGH RISK", 70)),
    ("college_valid", ("LOW", "VERIFIED", 0)),
    ("college_tampered", ("HIGH", "HIGH RISK", 70)),
]:
    resp = c.post("/api/verify/synthetic", json={"synthetic_id": sid}, headers=H)
    assert resp.status_code == 200, f"{sid}: {resp.status_code} {resp.text}"
    d = resp.json()
    rk = d["risk"]
    lvl, dec, score = expect
    assert rk["level"] == lvl, f"{sid}: level {rk['level']} != {lvl}"
    assert rk["decision"] == dec, f"{sid}: decision {rk['decision']} != {dec}"
    assert rk["score"] == score, f"{sid}: score {rk['score']} != {score}"
    assert d["image_url"].startswith("/media/samples/synthetic_"), f"{sid}: bad image_url {d['image_url']}"
    assert d["verification_id"], f"{sid}: no verification_id"
    terms = " ".join(rk.get("reasons", []))
    if dec == "HIGH RISK":
        assert "Possible document tampering detected" in terms, f"{sid}: missing tamper reason"
    print(f"{sid:18s} OK -> {lvl}/{dec} score={score} image={d['image_url']}")

# Unknown id should 400
r2 = c.post("/api/verify/synthetic", json={"synthetic_id": "bogus"}, headers=H)
assert r2.status_code == 400, f"unknown id: {r2.status_code}"
print("unknown synthetic_id -> 400 OK")
print("SYNTHETIC API TESTS PASSED")
