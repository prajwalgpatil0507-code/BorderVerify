import json, urllib.request, urllib.error, urllib.parse

BASE = "http://127.0.0.1:8000/api"

def call(method, path, body=None, token=None, form=False):
    data = None
    headers = {}
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"error": "non-json"}

st, login = call("POST", "/auth/login", {"username": "officer", "password": "SIH@2026Demo"}, form=True)
print("LOGIN", st, "keys:", sorted(login.keys()))
token = login.get("access_token")
print("token present:", bool(token))

st, stats = call("GET", "/dashboard/statistics", token=token)
print("STATS", st, stats)
need = {"total_verifications","verified","review_required","high_risk","fraud_detected","average_verification_time_seconds"}
print("  expected keys ok:", need <= set((stats or {}).keys()))

st, hist = call("GET", "/verification/history?limit=5", token=token)
print("HISTORY", st, "count:", len(hist) if isinstance(hist, list) else hist)
if isinstance(hist, list) and hist:
    print("  fields:", sorted(hist[0].keys()))

st, sv = call("POST", "/verify/synthetic", {"synthetic_id": "aadhaar_valid"}, token=token)
print("SYNTH valid", st, "keys:", sorted(sv.keys()))
print("  risk:", sv.get("risk"), "backend:", sv.get("backend"), "label:", sv.get("synthetic_label"), "vid:", sv.get("verification_id"))
t = sv.get("tamper", {})
print("  tamper overall:", t.get("overall_score"), "level:", t.get("risk_level"), "signals:", [s.get("name") for s in t.get("signals", [])])

st, st2 = call("POST", "/verify/synthetic", {"synthetic_id": "aadhaar_tampered"}, token=token)
print("SYNTH tampered", st, "risk:", st2.get("risk"), "backend:", st2.get("backend"))
t2 = st2.get("tamper", {})
print("  tamper overall:", t2.get("overall_score"), "level:", t2.get("risk_level"), "signals:", [s.get("name") for s in t2.get("signals", [])])

st, ov = call("GET", "/database/overview", token=token)
print("DB OVERVIEW", st, "keys:", sorted(ov.keys()))
print("  storage:", ov.get("storage"), "db:", ov.get("database"), "label:", ov.get("label"), "counts:", ov.get("counts"))

st, cols = call("GET", "/database/collections", token=token)
print("DB COLS", st, "n:", len(cols.get("collections", [])))
if cols.get("collections"):
    print("  first:", {k: cols["collections"][0].get(k) for k in ("name", "count")})

st, al = call("GET", "/alerts", token=token)
print("ALERTS", st, "n:", len(al) if isinstance(al, list) else al)
if isinstance(al, list) and al:
    print("  fields:", sorted(al[0].keys()), al[0].get("severity"), al[0].get("title"))

print("DONE")
