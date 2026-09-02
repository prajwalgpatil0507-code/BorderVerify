import time, httpx, json, sys

BASE = "http://127.0.0.1:8000"
def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + '\n'); sys.stdout.flush()

# wait for server
for i in range(30):
    try:
        r = httpx.get(BASE + "/api/health", timeout=2)
        if r.status_code == 200:
            log("server up:", r.json()); break
    except Exception:
        pass
    time.sleep(1)
else:
    log("SERVER NOT UP"); sys.exit(1)

# login
r = httpx.post(BASE + "/api/auth/login", data={"username":"officer","password":"officer123"}, timeout=10)
log("login status:", r.status_code)
tok = r.json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# upload valid passport
with open("../data/samples/valid_passport.png", "rb") as f:
    r = httpx.post(BASE + "/api/upload-document", files={"file":("valid.png", f, "image/png")}, timeout=30)
log("upload status:", r.status_code, r.json().get("filename") if r.status_code==200 else r.text)
fn = r.json()["filename"]

# verify document
r = httpx.post(BASE + "/api/verify/document", json={"image_filename":fn,"document_type":"auto"}, headers=H, timeout=90)
log("verify status:", r.status_code)
if r.status_code == 200:
    res = r.json()
    log("  verdict:", res["risk"]["decision"], "score", res["risk"]["score"], "id", res["verification_id"])
else:
    log("  ERR:", r.text)

# demo case
r = httpx.post(BASE + "/api/verify/demo", json={"scenario":"face_mismatch"}, headers=H, timeout=30)
log("demo face_mismatch:", r.status_code, r.json().get("risk",{}).get("decision") if r.status_code==200 else r.text)

# history
r = httpx.get(BASE + "/api/verification/history", headers=H, timeout=10)
log("history count:", len(r.json()))
log("last:", json.dumps(r.json()[0], default=str)[:160] if r.json() else "none")

# statistics
r = httpx.get(BASE + "/api/dashboard/statistics", headers=H, timeout=10)
log("stats:", r.json())

# alerts
r = httpx.get(BASE + "/api/alerts", headers=H, timeout=10)
log("alerts:", len(r.json()))

# frontend index served
r = httpx.get(BASE + "/", timeout=10)
log("index status:", r.status_code, "length", len(r.text))
log("ALL API TESTS COMPLETE")
