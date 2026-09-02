import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cv2
import numpy as np
from app.services import document_anomaly as da

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLES = os.path.join(ROOT, "data", "samples")

names = [
    "synthetic_aadhaar_valid.png", "synthetic_aadhaar_tampered.png",
    "synthetic_pan_valid.png", "synthetic_pan_tampered.png",
    "synthetic_collegeid_valid.png", "synthetic_collegeid_tampered.png",
]
for n in names:
    img = cv2.imdecode(np.fromfile(os.path.join(SAMPLES, n), dtype=np.uint8), cv2.IMREAD_COLOR)
    res = da.analyze(img, "", {})
    t = res.tamper
    sigs = ", ".join(f"{s.name}={s.score:.0f}/{s.level}" for s in t.signals)
    print(f"{n:45s} score={t.overall_score:5.1f} level={t.risk_level:7s} sigs=[{sigs}]")
    for r in res.reasons:
        print(f"      reason: {r}")
