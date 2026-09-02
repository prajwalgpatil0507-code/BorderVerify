import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services import orchestrator

for sid in ["aadhaar_valid", "aadhaar_tampered",
            "pan_valid", "pan_tampered",
            "college_valid", "college_tampered"]:
    r = orchestrator.verify_synthetic_document(sid)
    risk = r["risk"]; t = r["tamper"]
    print(f"{sid:18s} type={r['document_type']:8s} risk={risk['score']:3d}"
          f" {risk['level']:6s} decision={risk['decision']:12s} tamper={t['overall_score']:5.1f}/{t['risk_level']}")
    for k in risk.get("reasons", []):
        print(f"       why: {k}")
