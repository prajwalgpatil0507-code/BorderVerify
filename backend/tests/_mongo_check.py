"""End-to-end check of the MongoDB-backed reference data + API."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app
from app.db import mongo as m

client = TestClient(app)


def main():
    print("mongo_available:", m.mongo_available())
    print("counts:", m.counts())

    # Health
    r = client.get("/api/health")
    print("health:", r.status_code, r.json())

    # Login
    r = client.post("/api/auth/login",
                    data={"username": "officer", "password": "SIH@2026Demo"})
    print("login:", r.status_code)
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    if not token:
        print("NO TOKEN - aborting")
        return

    # Database overview
    r = client.get("/api/database/overview", headers=headers)
    print("overview:", r.status_code, r.json())

    # Collections
    r = client.get("/api/database/collections", headers=headers)
    print("collections:", r.status_code, [c["name"] + "=" + str(c["count"])
                                          for c in r.json().get("collections", [])])

    # Lookup a known scenario doc
    r = client.get("/api/database/lookup/P1234567", headers=headers)
    print("lookup P1234567:", r.status_code, r.json().get("matched_sources"))

    r = client.get("/api/database/lookup/PAXXXXXXX", headers=headers)
    print("lookup PAXXXXXXX:", r.status_code, r.json().get("matched_sources"))

    # system-config
    r = client.get("/api/database/system-config", headers=headers)
    print("system-config:", r.status_code, r.json()["config"])
    print("DONE")


if __name__ == "__main__":
    main()
