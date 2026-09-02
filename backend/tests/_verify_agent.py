import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)

from fastapi.testclient import TestClient
from app.main import app

SAMPLE = os.path.join(ROOT, 'data', 'samples', 'valid_passport.png')
UPLOADS = os.path.join(ROOT, 'data', 'uploads')

def log(*a):
    sys.stdout.write(' '.join(str(x) for x in a) + chr(10))
    sys.stdout.flush()

results = []

def record(step, status, extra=''):
    results.append((step, status, extra))
    log(f'  -> [{step}] status={status} {extra}')

client = TestClient(app)

r = client.post('/api/auth/login', data={'username': 'officer', 'password': 'SIH@2026Demo'})

tok = r.json().get('access_token', '') if r.status_code == 200 else ''...
record('login', r.status_code, f'access_token_len={len(tok)} role={r.json().get('role') if r.status_code == 200 else r.text}')

assert r.status_code == 200, f'login failed: {r.status_code} {r.text}'
assert tok, 'no access_token returned'
headers = {'Authorization': 'Bearer ' + tok}

with open(SAMPLE, 'rb') as f:
    ru = client.post('/api/upload-document', files={'file': ('valid_passport.png', f, 'image/png')})
fn = ru.json().get('filename', '') if ru.status_code == 200 else ''...
upath = Path(UPLOADS, fn)
record('upload-document', ru.status_code, f'filename={fn} starts_doc={fn.startswith('doc_')} file_exists={upath.exists()} size={upath.stat().st_size if upath.exists() else -1}')

assert ru.status_code == 200, f'upload failed: {ru.status_code} {ru.text}'
assert fn.startswith('doc_'), f'filename does not start with doc_: {fn}'
assert upath.exists(), f'uploaded file not physically present: {upath}'
body = ru.json()
record('upload-document-body', ru.status_code, f'file_id={body.get('file_id')} file_type={body.get('file_type')} size_bytes={body.get('size_bytes')}')

ro = client.post('/api/ocr/extract', data={'filename': fn}, headers=headers)
ocr_text = ro.json().get('text', '') if ro.status_code == 200 else ''...
record('ocr/extract', ro.status_code, f'text_len={len(ocr_text)} sample={ocr_text[:50]!r} confidence={ro.json().get('confidence') if ro.status_code == 200 else ro.text}')

assert ro.status_code == 200, f'ocr failed: {ro.status_code} {ro.text}'
assert len(ocr_text) > 0, 'OCR returned empty text'

rv = client.post('/api/verify/document', json={'image_filename': fn, 'document_type': 'auto'}, headers=headers)
risk = rv.json().get('risk', {}) if rv.status_code == 200 else {}

record('verify/document', rv.status_code, f'decision={risk.get('decision')} score={risk.get('score')} level={risk.get('level')} verification_id={rv.json().get('verification_id') if rv.status_code == 200 else rv.text}')
assert rv.status_code == 200, f'verify failed: {rv.status_code} {rv.text}'
assert 'decision' in risk, f'risk.decision missing: {list(risk.keys())}'

rh = client.get('/api/verification/history', headers=headers)
rows = rh.json() if rh.status_code == 200 else []
record('verification/history', rh.status_code, f'row_count={len(rows)} first={rows[0] if rows else None}')
assert rh.status_code == 200, f'history failed: {rh.status_code} {rh.text}'
assert isinstance(rows, list), f'history not a list: {type(rows)}'

vid = rv.json().get('verification_id')
if vid is not None:
    rs = client.get(f'/api/verification/{vid}', headers=headers)
    record('verification/{id}', rs.status_code, f'has_risk={'risk' in rs.json() if rs.status_code == 200 else rs.text}')
    assert rs.status_code == 200, f'single verify failed: {rs.status_code} {rs.text}'

log(chr(10) + '=== SUMMARY ===')
all_ok = True
for step, status, extra in results:
    ok = status == 200
    all_ok = all_ok and ok
    log(f'  [{step}] status={status} {'OK' if ok else 'FAIL'}  {extra}')

log(chr(10) + 'RESULT: ' + ('PASS' if all_ok else 'FAIL'))
sys.exit(0 if all_ok else 1)
