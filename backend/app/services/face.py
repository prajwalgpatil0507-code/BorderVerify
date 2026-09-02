"""Face detection and identity-matching service.

The prototype uses OpenCV's bundled Haar cascade for real face *detection* and a
histogram / LBP descriptor for *similarity* (embedding).  This is a legitimate
image-similarity approach but it is **not** a deep-trained face-recognition
embedding.  The result is explicitly labelled DEMO/HUERISTIC so nobody mistakes
it for production-grade biometric accuracy.

If a production embedding model (e.g. InsightFace, FaceNet) is later installed,
``embeddings.py`` can be swapped in without changing the interface.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import cv2


@dataclass
class FaceDetection:
    boxes: list = field(default_factory=list)   # [x, y, w, h]
    count: int = 0

    def to_dict(self) -> dict:
        return {"boxes": self.boxes, "count": self.count}


@dataclass
class FaceMatch:
    similar: bool
    score: float            # 0..1
    status: str             # match | review | mismatch | no_face
    message: str
    provided: FaceDetection = field(default_factory=FaceDetection)
    reference: FaceDetection = field(default_factory=FaceDetection)

    def to_dict(self) -> dict:
        return {
            "similar": self.similar,
            "score": round(self.score, 4),
            "status": self.status,
            "message": self.message,
            "provided_faces": self.provided.to_dict(),
            "reference_faces": self.reference.to_dict(),
        }


# --- Bundled models are downloaded into the backend dir on first setup ---
from ..config import BASE_DIR  # noqa: E402

_MODEL_PATH = os.path.join(str(BASE_DIR), "cv2_yunet.onnx")

_DETECTOR = None


def _get_detector():
    """Lazily build a FaceDetectorYN (YuNet) DNN detector."""
    global _DETECTOR
    if _DETECTOR is not None:
        return _DETECTOR
    if not os.path.exists(_MODEL_PATH):
        return None
    try:
        _DETECTOR = cv2.FaceDetectorYN.create(
            _MODEL_PATH, "", (320, 320), 0.9, 0.3, 5000)
    except Exception:  # noqa: BLE001
        _DETECTOR = None
    return _DETECTOR


class NoFaceError(RuntimeError):
    pass


def detect_faces(matrix: np.ndarray) -> FaceDetection:
    """Detect faces in an image (BGR/gray) using YuNet DNN.

    Falls back to an empty result (count 0) if the detector/model is missing.
    """
    detector = _get_detector()
    if detector is None:
        return FaceDetection()
    if matrix is None or matrix.size == 0:
        return FaceDetection()
    bgr = matrix if matrix.ndim == 3 else cv2.cvtColor(matrix, cv2.COLOR_GRAY2BGR)
    bgr = cv2.resize(bgr, (320, 320), interpolation=cv2.INTER_AREA)
    try:
        _ok, faces = detector.detect(bgr)
    except Exception:  # noqa: BLE001
        return FaceDetection()
    if faces is None:
        return FaceDetection()
    boxes = []
    for f in faces:
        # YuNet returns [x, y, w, h, ...landmarks] in image coords.
        x, y, w, h = int(f[0]), int(f[1]), int(f[2]), int(f[3])
        boxes.append([x, y, w, h])
    return FaceDetection(boxes=boxes, count=len(boxes))


def _crop_face(matrix: np.ndarray, box) -> np.ndarray:
    x, y, w, h = box
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(matrix.shape[1], x + w), min(matrix.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    return matrix[y0:y1, x0:x1]


def _face_descriptor(matrix: np.ndarray, box) -> Optional[np.ndarray]:
    """Build a normalised similarity descriptor for a face region.

    Combines a resized luminance patch with an LBP histogram.  This is a
    *heuristic* descriptor used for the prototype's demo matching.
    """
    crop = _crop_face(matrix, box)
    if crop is None or crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    try:
        sub = detect_faces(crop)
        if sub.count and len(sub.boxes):
            x, y, w, h = sub.boxes[0]
            gray = gray[y:y + h, x:x + w]
    except Exception:  # noqa: BLE001
        pass

    gray = cv2.resize(gray, (96, 96), interpolation=cv2.INTER_AREA)
    lum = gray.flatten().astype(np.float32) / 255.0
    lum = lum - lum.mean()
    if lum.std() > 1e-6:
        lum /= lum.std()

    # LBP texture histogram
    lbp = _local_binary_pattern(gray)
    hist, _ = np.histogram(lbp, bins=16, range=(0, 16), density=True)
    if hist.max() > 0:
        hist /= hist.max()

    descriptor = np.concatenate([lum, hist.astype(np.float32)])
    return descriptor


def _local_binary_pattern(gray: np.ndarray, radius: int = 1) -> np.ndarray:
    """Simplified local binary pattern for the whole face region."""
    g = gray.astype(np.int32)
    lbp = np.zeros_like(g)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = np.roll(np.roll(g, dy, axis=0), dx, axis=1)
            bit = (shifted >= g).astype(np.int32)
            idx = (dy + radius) * (2 * radius + 1) + (dx + radius)
            lbp += bit << idx
    return lbp.astype(np.uint8)


def _similarity(desc_a: np.ndarray, desc_b: np.ndarray) -> float:
    """Cosine similarity between two descriptors, mapped to 0..1."""
    if desc_a is None or desc_b is None:
        return 0.0
    a, b = desc_a.astype(np.float64), desc_b.astype(np.float64)
    if a.shape != b.shape:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    cos = float(np.dot(a, b) / (na * nb))
    return float(np.clip((cos + 1.0) / 2.0, 0.0, 1.0))


def match_faces(reference: np.ndarray, provided: np.ndarray,
                threshold: float = 0.62,
                review_threshold: float = 0.78) -> FaceMatch:
    """Match a reference (passport photo) against a provided live/upload photo.

    Returns a FaceMatch with score/status.  Thresholds come from settings.
    """
    ref_det = detect_faces(reference)
    prov_det = detect_faces(provided)

    if ref_det.count == 0:
        return FaceMatch(similar=False, score=0.0, status="no_face",
                         message="No face detected in the passport photo.",
                         provided=prov_det, reference=ref_det)
    if prov_det.count == 0:
        return FaceMatch(similar=False, score=0.0, status="no_face",
                         message="No face detected in the provided photo.",
                         provided=prov_det, reference=ref_det)

    ref_desc = _face_descriptor(reference, ref_det.boxes[0])
    # Pick the best matching provided face
    best_score = 0.0
    for box in prov_det.boxes:
        prov_desc = _face_descriptor(provided, box)
        score = _similarity(ref_desc, prov_desc)
        best_score = max(best_score, score)

    status = "mismatch"
    if best_score >= review_threshold:
        status = "match"
    elif best_score >= threshold:
        status = "review"

    similar = status == "match"
    message = {
        "match": f"Face match: {int(best_score * 100)}% - PASS.",
        "review": f"Face match: {int(best_score * 100)}% - manual review required.",
        "mismatch": f"Face match: {int(best_score * 100)}% - potential identity mismatch.",
    }[status]

    return FaceMatch(similar=similar, score=best_score, status=status,
                     message=message, provided=prov_det, reference=ref_det)
