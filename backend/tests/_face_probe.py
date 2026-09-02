import sys, os, cv2
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.services.face import detect_faces, match_faces, _face_descriptor, _similarity
from app.config import settings

def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + '\n'); sys.stdout.flush()

ref = cv2.imread(os.path.join('data','samples','ref_face.png'))
prov = cv2.imread(os.path.join('data','samples','provided_face.png'))

rd = detect_faces(ref)
pd = detect_faces(prov)
log("ref faces:", rd.count, rd.boxes)
log("prov faces:", pd.count, pd.boxes)

if rd.count and pd.count:
    d1 = _face_descriptor(ref, rd.boxes[0])
    for b in pd.boxes:
        d2 = _face_descriptor(prov, b)
        log("similarity:", round(_similarity(d1, d2), 3))
    m = match_faces(ref, prov, settings.FACE_MATCH_THRESHOLD, settings.FACE_REVIEW_THRESHOLD)
    log("match:", m.status, round(m.score,3), m.message)
else:
    log("Face detection did not find faces on synthetic images (expected for demo).")
    log("Face verification path will be exercised via demo face_score instead.")
