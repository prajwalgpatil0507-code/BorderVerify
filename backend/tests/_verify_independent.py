import json, urllib.request, urllib.parse, urllib.error
BASE = "http://127.0.0.1:8000/api"

def req(method, path, token=None, data=None, form=False):
    url = BASE + path
    headers = {}
    body = None
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return None, str(e)

ok = lambda cond: ("PASS" if cond else "FAIL")

# 1. login
code, data = req("POST", "/auth/login", data={"username": "officer", "password": "SIH@2026Demo"}, form=True)
print("login:", code, ok(code == 200 and "access_token" in data))
tok = data["access_token"] if isinstance(data, dict) else None

# 2. dashboard/statistics
code, data = req("GET", "/dashboard/statistics", token=tok)
keys = ["total_verifications","verified","review_required","high_risk","fraud_detected","average_verification_time_seconds"]
present = all(k in data for k in keys) if isinstance(data, dict) else False
print("dashboard/statistics:", code, ok(code == 200 and present), "keys_present=%s" % present)

# 3. history
code, data = req("GET", "/verification/history?limit=5", token=tok)
hkeys = ["id","passenger_name","document_number","document_type","nationality","risk_score","risk_level","decision","created_at"]
first_ok = False
if code == 200 and isinstance(data, list) and data:
    first_ok = all(k in data[0] for k in hkeys)
print("verification/history:", code, ok(code == 200 and isinstance(data, list) and first_ok if code == 200 else False),
      "list_len=%s" % (len(data) if isinstance(data, list) else "n/a"), "first_keys_ok=%s" % first_ok)

# 4. synthetic aadhaar_valid
code, data = req("POST", "/verify/synthetic", token=tok, data={"synthetic_id": "aadhaar_valid"})
if code == 200 and isinstance(data, dict):
    r, t = data["risk"], data["tamper"]
    cond = (data.get("backend") == "synthetic-image" and r["decision"] == "VERIFIED" and r["level"] == "LOW"
            and r["score"] == 0 and t["overall_score"] == 0 and len(t.get("signals", [])) == 0)
else:
    cond = False
print("synthetic aadhaar_valid:", code, ok(cond),
      "backend=%s decision=%s level=%s score=%s tamper=%s sigs=%d" % (
          data.get("backend") if isinstance(data, dict) else "?",
          data.get("risk",{}).get("decision") if isinstance(data, dict) else "?",
          data.get("risk",{}).get("level") if isinstance(data, dict) else "?",
          data.get("risk",{}).get("score") if isinstance(data, dict) else "?",
          data.get("tamper",{}).get("overall_score") if isinstance(data, dict) else "?",
          len(data.get("tamper",{}).get("signals",[])) if isinstance(data, dict) else 0))

# 5. synthetic aadhaar_tampered
code, data = req("POST", "/verify/synthetic", token=tok, data={"synthetic_id": "aadhaar_tampered"})
if code == 200 and isinstance(data, dict):
    r, t = data["risk"], data["tamper"]
    reasons = " ".join(r.get("reasons", []))
    cond = (data.get("backend") == "synthetic-image" and r["decision"] == "HIGH RISK" and r["level"] == "HIGH"
            and r["score"] == 70 and t["overall_score"] > 0 and len(t.get("signals", [])) > 0
            and "Possible document tampering detected" in reasons)
    print("synthetic aadhaar_tampered:", code, ok(cond),
          "backend=%s decision=%s level=%s score=%s tamper=%.1f sigs=%d reason_found=%s" % (
              data.get("backend"), r["decision"], r["level"], r["score"], t["overall_score"],
              len(t.get("signals", [])), "Possible document tampering detected" in reasons))
else:
    print("synthetic aadhaar_tampered:", code, ok(False), "resp=%s" % (data if isinstance(data, str) else data))

# 6. database overview
code, data = req("GET", "/database/overview", token=tok)
if code == 200 and isinstance(data, dict):
    cond = (data.get("storage") == "MongoDB" and data.get("database") == "borderverify"
            and data.get("label") == "SIH SYNTHETIC DEMO DATABASE" and isinstance(data.get("counts"), dict))
else:
    cond = False
print("database/overview:", code, ok(cond),
      "storage=%s db=%s label=%s counts_is_dict=%s" % (
          data.get("storage") if isinstance(data, dict) else "?", data.get("database") if isinstance(data, dict) else "?",
          data.get("label") if isinstance(data, dict) else "?", isinstance(data.get("counts"), dict) if isinstance(data, dict) else False))

# 7. database collections
code, data = req("GET", "/database/collections", token=tok)
if code == 200 and isinstance(data, dict):
    cols = data.get("collections", [])
    cond = len(cols) == 8 and all("name" in c and "count" in c for c in cols)
else:
    cols, cond = [], False
print("database/collections:", code, ok(cond), "n_collections=%s" % len(cols),
      "names=%s" % [c.get("name") for c in cols])

# 8. alerts
code, data = req("GET", "/alerts", token=tok)
if code == 200 and isinstance(data, list):
    cond = all("severity" in a and "title" in a and "message" in a and "created_at" in a for a in data) if data else True
else:
    cond = False
print("alerts:", code, ok(cond), "len=%s" % (len(data) if isinstance(data, list) else "n/a"))
