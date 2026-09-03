"""Download the InsightFace ArcFace face-recognition embedding model.

The prototype ships a *heuristic* face matcher (LBP + luminance) in
``backend/app/services/face.py``.  A real deep face-recognition embedding
(e.g. InsightFace / ArcFace) can be swapped in by dropping the recognition
ONNX model at ``backend/arcface_w600k_r50.onnx``.

This script fetches the official InsightFace ``buffalo_l`` model pack and
extracts ONLY the ArcFace recognition model (512-d embeddings).  Detection and
alignment are handled in-process (YuNet + a similarity transform), so we don't
need the rest of the pack.

The model is ~166 MB, so it is NOT committed to git -- it is downloaded locally.
"""

import sys
import io
import urllib.request
import zipfile
import os

MODEL_URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
DEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
MODEL_NAME = "arcface_w600k_r50.onnx"
MODEL_DEST = os.path.join(DEST_DIR, MODEL_NAME)

# Inside the zip the recognition model is at this path.
ZIP_INSIDE = "w600k_r50.onnx"


def log(*a):
    sys.stdout.write(" ".join(str(x) for x in a) + "\n")
    sys.stdout.flush()


def main():
    if os.path.exists(MODEL_DEST) and os.path.getsize(MODEL_DEST) > 1_000_000:
        log("exists", MODEL_DEST, os.path.getsize(MODEL_DEST), "bytes")
        _verify()
        return

    os.makedirs(DEST_DIR, exist_ok=True)
    log("downloading", MODEL_URL)
    data = urllib.request.urlretrieve(MODEL_URL)[0]
    # urlretrieve returns a temp file name; re-open as zip.
    log("downloaded zip ->", data)
    _extract(data)


def _extract(zip_path: str):
    with zipfile.ZipFile(zip_path) as zf:
        if ZIP_INSIDE not in zf.namelist():
            log("ERROR: %s not found in zip. Contents: %s" % (
                ZIP_INSIDE, ", ".join(zf.namelist())))
            sys.exit(1)
        with zf.open(ZIP_INSIDE) as src, open(MODEL_DEST, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)
        log("extracted", MODEL_NAME, "->", MODEL_DEST, os.path.getsize(MODEL_DEST), "bytes")
    _verify()


def _verify():
    try:
        import onnxruntime as ort
        sess = ort.InferenceSession(MODEL_DEST, providers=["CPUExecutionProvider"])
        log("ONNX session created OK. input:", sess.get_inputs()[0].name,
            sess.get_inputs()[0].shape)
    except Exception as e:  # noqa: BLE001
        log("verify failed:", repr(e))


if __name__ == "__main__":
    main()
