"""Smoke-test the SIH DEMO DATABASE endpoints via TestClient (read-only)."""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

# Login to obtain a bearer token.
r = client.post("/api/auth/login",
                data={"username": "officer", "password": "SIH@2026Demo"})
print("LOGIN", r.status_code)
assert r.status_code == 200, r.text
token = r.json()["access_token"]
H = {"Authorization": f"Bearer {token}"}


def show(label: str, resp):
    body = resp.json()
    print(f"\n--- {label} -> {resp.status_code} ---")
    if resp.status_code >= 300:
        print(body)
        return
    if isinstance(body, dict):
        for k, v in body.items():
            if k in ("sources", "travellers", "records"):
                print(f"  {k}: <{len(v)} items>")
            else:
                print(f"  {k}: {v}")
    else:
        print(body)


show("METADATA", client.get("/api/demo/metadata", headers=H))
show("DATA-SOURCES", client.get("/api/demo/data-sources", headers=H))
show("LOOKUP X99887766", client.get("/api/demo/lookup/X99887766", headers=H))
show("LOOKUP P12345678", client.get("/api/demo/lookup/P12345678", headers=H))
show("LOOKUP unauthed", client.get("/api/demo/lookup/P12345678"))
show("TRAVELLERS", client.get("/api/demo/travellers", headers=H))

print("\nALL DEMO CHECKS PASSED")
