"""Deep face-recognition embedding provider (ArcFace / InsightFace).

This swaps the heuristic LBP + luminance descriptor in ``face.py`` for a
pre-trained ArcFace (InsightFace ``w600k_r50``) embedding.  It is a frozen,
download-only model -- *training* a face-recognition model requires a large
labelled dataset (thousands of identities) and is intentionally out of scope
for this prototype.  The model is fetched by ``_download_arcface.py``.

``embedding_match`` mirrors the signature and contract of ``face.match_faces``
so the exchange is transparent to the rest of the application.  If the model is
not present, ``face.match_faces`` silently falls back to the heuristic.
"""
from __future__ import annotations

import os

import numpy as np
import cv2

from ..config import settings
from .face import FaceMatch, detect_faces

_SESSION = None
_LOADED_PATH = None

# ArcFace alignment template (right eye, left eye, nose, right mouth, left mouth)
# in the same order YuNet returns landmarks.
_ARC_DEST = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)


class EmbeddingModelUnavailable(RuntimeError):
    """Raised when the ArcFace model (or runtime) cannot be used."""


def model_path() -> str:
    return str(settings.FACE_EMBEDDING_MODEL)


def _get_session():
    global _SESSION, _LOADED_PATH
    path = model_path()
    if _SESSION is not None and _LOADED_PATH == path:
        return _SESSION
    if not os.path.exists(path):
        raise EmbeddingModelUnavailable(f"model not found: {path}")
    try:
        import onnxruntime as ort
    except Exception as e:  # noqa: BLE001
        raise EmbeddingModelUnavailable(f"onnxruntime not installed: {e!r}")
    try:
        _SESSION = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    except Exception as e:  # noqa: BLE001
        raise EmbeddingModelUnavailable(f"failed to load model: {e!r}")
    _LOADED_PATH = path
    return _SESSION


def available() -> bool:
    try:
        _get_session()
        return True
    except Exception:  # noqa: BLE001
        return False


def norm_crop(img: np.ndarray, landmarks, image_size: int = 112) -> np.ndarray:
    """Align a 112x112 face crop from 5 landmarks (InsightFace ``norm_crop``)."""
    lmk = np.array(landmarks, dtype=np.float32)
    if lmk.shape != (5, 2):
        raise ValueError(f"expected 5x2 landmarks, got {lmk.shape}")
    M, _ = cv2.estimateAffinePartial2D(lmk, _ARC_DEST)
    if M is None:
        raise ValueError("face alignment failed")
    return cv2.warpAffine(img, M, (image_size, image_size), borderValue=0.0)


def _preprocess(crop: np.ndarray) -> np.ndarray:
    """BGR 112x112 crop -> NCHW float in [-1, 1] (RGB), as InsightFace expects."""
    blob = cv2.dnn.blobFromImage(
        crop, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
    return blob.astype(np.float32)


def get_embedding(crop: np.ndarray) -> np.ndarray:
    """Return an L2-normalised 512-d embedding for an aligned face crop."""
    sess = _get_session()
    input_name = sess.get_inputs()[0].name
    output_name = sess.get_outputs()[0].name
    emb = sess.run([output_name], {input_name: _preprocess(crop)})[0][0]
    emb = emb.astype(np.float64)
    n = float(np.linalg.norm(emb))
    if n > 1e-9:
        emb /= n
    return emb


def _embed_largest(img: np.ndarray):
    """Detect faces, align the largest, return (embedding, detection).

    Returns ``(None, detection)`` when no face is found.
    """
    det = detect_faces(img)
    if det.count == 0 or not det.landmarks:
        return None, det
    best_i = 0
    best = det.boxes[0][2] * det.boxes[0][3]
    for i, b in enumerate(det.boxes):
        area = b[2] * b[3]
        if area > best:
            best, best_i = area, i
    crop = norm_crop(img, det.landmarks[best_i])
    return get_embedding(crop), det


def embedding_match(reference: np.ndarray, provided: np.ndarray,
                    threshold: float = 0.62,
                    review_threshold: float = 0.78) -> FaceMatch:
    """Deep-embedding face match, same contract as ``face.match_faces``."""
    ref_emb, ref_det = _embed_largest(reference)
    prov_emb, prov_det = _embed_largest(provided)

    if ref_emb is None:
        return FaceMatch(similar=False, score=0.0, status="no_face",
                         message="No face detected in the passport photo.",
                         provided=prov_det, reference=ref_det)
    if prov_emb is None:
        return FaceMatch(similar=False, score=0.0, status="no_face",
                         message="No face detected in the provided photo.",
                         provided=prov_det, reference=ref_det)

    cos = float(np.dot(ref_emb, prov_emb))
    score = (cos + 1.0) / 2.0  # map [-1, 1] -> [0, 1]

    if score >= review_threshold:
        status = "match"
    elif score >= threshold:
        status = "review"
    else:
        status = "mismatch"

    similar = status == "match"
    pct = int(score * 100)
    message = {
        "match": f"Face match: {pct}% similarity - PASS.",
        "review": f"Face match: {pct}% similarity - manual review required.",
        "mismatch": f"Face match: {pct}% similarity - potential identity mismatch.",
    }[status]

    return FaceMatch(similar=similar, score=score, status=status,
                     message=message, provided=prov_det, reference=ref_det)
