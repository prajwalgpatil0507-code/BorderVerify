import os, sys, json, urllib.request, urllib.parse
BASE = "http://127.0.0.1:8000"

def req(method, path, token=None, data=None, form=False):
    url = BASE + path
    headers = {}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

s = req("POST", "/api/auth/login", data={"username": "officer", "password": "SIH@2026Demo"}, form=True)
assert s[0] == 200, s
tok = s[1]["access_token"]
print("login OK")

for sid, expect in [("aadhaar_valid", "VERIFIED"), ("aadhaar_tampered", "HIGH RISK"),
                    ("pan_tampered", "HIGH RISK"), ("college_valid", "VERIFIED")]:
    code, d = req("POST", "/api/verify/synthetic", token=tok, data={"synthetic_id": sid})
    assert code == 200, (code, d)
    assert d["risk"]["decision"] == expect, (sid, d["risk"]["decision"])
    print(f"{sid:18s} {d['risk']['level']:6s} {d['risk']['decision']:12s} score={d['risk']['score']} backend={d['backend']}")

# passport demo still healthy
code, d = req("POST", "/api/verify/demo", token=tok, data={"scenario": "valid"})
assert code == 200, (code, d)
print("demo valid ->", d["risk"]["decision"], "score", d["risk"]["score"], "backend", d["backend"])
print("LIVE SYNTHETIC + DEMO SWITCH CHECK PASSED")
