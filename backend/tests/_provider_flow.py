"""Integration test: verify the live pipeline reads from the SIH DEMO DATABASE.

Covers the complete flow (image/FMZ -> providers -> risk) and the four required
cases.  Run with Python 3.10:  py -3.10 backend/tests/_provider_flow.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient          # noqa: E402
from app.main import app                           # noqa: E402
from app.services import orchestrator              # noqa: E402
from app.services import providers as prov         # noqa: E402

SAMPLES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                       "data", "samples"))

client = TestClient(app)
r = client.post("/api/auth/login",
                data={"username": "officer", "password": "SIH@2026Demo"})
assert r.status_code == 200, r.text
H = {"Authorization": f"Bearer {r.json()['access_token']}"}


def heading(t):
    print(f"\n{'='*74}\n{t}\n{'='*74}")


def summary(res):
    ds = res.get("data_source", "?")
    env = res.get("environment", "?")
    risk = res.get("risk", {})
    prov_src = res.get("source_provenance", {})
    checks = {c["check"]: (c["provider"], c["table"], c["matched"])
              for c in prov_src.get("checks", [])}
    print(f"  data_source={ds}  environment={env}")
    for check in ("passport", "visa", "watchlist", "duplicate_identity"):
        p, t, m = checks.get(check, ("?", "?", "?"))
        print(f"    {check:<20} <- {p:<20} table={t:<18} matched={m}")
    print(f"  RISK score={risk.get('score')} level={risk.get('level')} "
          f"decision={risk.get('decision')}")
    print(f"  contributions={[c['signal'] for c in risk.get('contributions',[]) if c['applied']]}")
    return ds, env, risk.get("decision")


# --- 1. Provider unit sanity (which table each provider reads) ---
heading("PROVIDER UNIT CHECKS")
pp = prov.DemoPassportProvider().lookup("P12345678")
print(f"DemoPassportProvider P12345678 -> found={pp.found} status={pp.status}"
      f" table={pp.table} source={pp.source}")
assert pp.found and pp.table == "passport_records" and pp.source == prov.SOURCE_LABEL
vp = prov.DemoVisaProvider().lookup("P12345678")
print(f"DemoVisaProvider P12345678 -> found={vp.found} status={vp.status} table={vp.table}")
assert vp.found and vp.table == "visa_records"
wl = prov.DemoWatchlistProvider().check("X99887766", "DEMOOS", "850101")
print(f"DemoWatchlistProvider X99887766 -> matched={wl.matched} category={wl.category} table={wl.table}")
assert wl.matched and wl.category == "watchlist" and wl.table == "watchlist_records"
dup = prov.DemoIdentityProvider().check(
    {"surname": "KUMAR", "given_names": "R K", "date_of_birth": "101003",
     "nationality": "IND", "document_number": "P11223399"})
print(f"DemoIdentityProvider KUMAR/P11223399 -> is_duplicate={dup.is_duplicate} "
      f"confidence={dup.confidence} table={dup.table}")
assert dup.is_duplicate and dup.table == "identity_records"

# --- 2. Live image flow (verify_image) on the four sample documents ---
heading("CASE 1 - VALID PASSPORT -> VERIFIED")
res = orchestrator.verify_image(os.path.join(SAMPLES, "valid_passport.png"))
ds, env, dec = summary(res)
assert res["passport"]["found"] is True, "valid passport should be found in demo DB"
assert res["watchlist"]["matched"] is False
assert dec == "VERIFIED", dec

heading("CASE 2 - WATCHLIST RECORD -> HIGH RISK")
res = orchestrator.verify_image(os.path.join(SAMPLES, "watchlist_passport.png"))
ds, env, dec = summary(res)
assert res["watchlist"]["matched"] is True, "watchlist sample should match demo watchlist"
assert dec == "HIGH RISK", dec

heading("CASE 3 - EXPIRED PASSPORT -> REVIEW REQUIRED")
res = orchestrator.verify_image(os.path.join(SAMPLES, "expired_passport.png"))
ds, env, dec = summary(res)
assert res["expiry"]["status"] == "expired", res["expiry"]
assert dec == "REVIEW REQUIRED", dec

heading("CASE 4 (via raw demo) - DUPLICATE IDENTITY -> REVIEW REQUIRED / HIGH RISK")
from app.schemas.schemas import RawVerifyRequest
res = orchestrator.verify_demo(RawVerifyRequest(scenario="duplicate"))
ds, env, dec = summary(res)
assert res["duplicate"]["is_duplicate"] is True
assert dec in ("REVIEW REQUIRED", "HIGH RISK"), dec

# --- 3. All results must proclaim the demo data source ---
heading("DATA-SOURCE / ENVIRONMENT LABELLING (all flows)")
for path, label in [("valid_passport.png", "VALID"),
                    ("watchlist_passport.png", "WATCHLIST"),
                    ("expired_passport.png", "EXPIRED")]:
    res = orchestrator.verify_image(os.path.join(SAMPLES, path))
    assert res["data_source"] == "SIH DEMO DATABASE", res
    assert res["environment"] == "DEMO / MOCK", res
    assert res["source_provenance"]["is_real_data"] is False
    print(f"  {label}: data_source={res['data_source']} env={res['environment']}")

# --- 4. Full API flow: upload -> verify/complete (live, via HTTP) ---
heading("FULL API FLOW - upload -> verify -> result")
with open(os.path.join(SAMPLES, "valid_passport.png"), "rb") as fh:
    up = client.post("/api/upload-document",
                     headers=H, files={"file": ("valid_passport.png", fh,
                                                "image/png")})
assert up.status_code == 200, up.text
fname = up.json()["filename"]
vc = client.post("/api/verify/complete", headers=H,
                 data={"filename": fname, "document_type": "passport"})
assert vc.status_code == 200, vc.text
body = vc.json()
assert body["data_source"] == "SIH DEMO DATABASE", body
assert body["environment"] == "DEMO / MOCK", body
assert body["risk"]["decision"] == "VERIFIED", body["risk"]["decision"]
print(f"  upload->verify decision={body['risk']['decision']} "
      f"score={body['risk']['score']} data_source={body['data_source']}")

# --- 5. All 7 demo scenarios still produce valid, consistent results ---
heading("ALL 7 DEMO SCENARIOS (verify/demo endpoint)")
for sc in ("valid", "expired", "mrz_mismatch", "face_mismatch", "tamper",
           "watchlist", "duplicate"):
    r = client.post("/api/verify/demo", headers=H,
                    json={"scenario": sc})
    assert r.status_code == 200, (sc, r.text)
    b = r.json()
    assert b.get("data_source") == "SIH DEMO DATABASE", (sc, b.get("data_source"))
    print(f"  {sc:<12} -> {b['risk']['decision']:<16} score={b['risk']['score']}")

print("\nALL PROVIDER/FLOW CHECKS PASSED")
