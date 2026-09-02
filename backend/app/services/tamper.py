"""Document authenticity / tampering analysis.

This prototype computes *heuristic* signals that are commonly used as evidence
of document manipulation:

* Splicing / copy-paste (JPEG + ELA error-level analysis)
* Photo-page uniformity and edge anomalies
* Compression noise consistency (ELA skew)
* Text insertion / deletion susceptibility

These are **signals**, not forensic-grade proof. The module clearly labels its
output as heuristic and the UI must reflect that.  No claim of certified
forensic detection is made anywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import cv2

from ..config import settings


@dataclass
class TamperSignal:
    name: str
    score: float          # 0..100 (higher = more suspicious)
    label: str            # "ok" | "suspicious" | "high"
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "label": self.label,
            "description": self.description,
        }


@dataclass
class TamperResult:
    overall_score: float = 0.0
    risk_level: str = "low"           # low | medium | high
    signals: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_score": round(self.overall_score, 1),
            "risk_level": self.risk_level,
            "signals": [s.to_dict() for s in self.signals],
            "notes": self.notes,
        }


def _to_gray(matrix: np.ndarray) -> np.ndarray:
    if matrix.ndim == 3:
        return cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    return matrix


def _resize_for_analysis(matrix: np.ndarray, max_dim: int) -> np.ndarray:
    """Downscale very large images before ELA / region analysis.

    Tampering signals (compression-noise skew, regional variance) are relative
    metrics, so operating on a bounded resolution keeps the heuristic meaningful
    while avoiding a slow full-resolution JPEG re-compression plus statistics on
    multi-megapixel uploads.
    """
    h, w = matrix.shape[:2]
    m = max(h, w)
    if m > max_dim > 0:
        scale = max_dim / m
        return cv2.resize(matrix, (int(w * scale), int(h * scale)),
                          interpolation=cv2.INTER_AREA)
    return matrix


def _ela_analysis(gray: np.ndarray, q: int = 80) -> np.ndarray:
    """Error Level Analysis approximation using JPEG recompression.

    Returns the per-pixel ELA magnitude scaled to 0..255 (uint8).
    """
    if gray.size == 0:
        return gray
    # Compress (simulate) then decompress to expose recompression noise.
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), q]
    ok, buf = cv2.imencode(".jpg", gray, encode_param)
    if not ok:
        return np.zeros_like(gray)
    recompressed = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    diff = cv2.absdiff(gray, recompressed)
    return diff


def analyze(matrix: np.ndarray, metadata: Optional[dict] = None) -> TamperResult:
    """Compute tamper heuristics for a document image.

    ``metadata`` may carry file-level information (e.g. EXIF) but is optional.
    """
    if matrix is None or matrix.size == 0:
        return TamperResult(overall_score=0, risk_level="low",
                            signals=[], notes=["No image provided."])
    matrix = _resize_for_analysis(
        matrix, int(getattr(settings, "TAMPER_MAX_DIM", 1200)))
    if matrix.ndim == 3:
        gray = cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
        color = matrix
    else:
        gray = matrix
        color = cv2.cvtColor(matrix, cv2.COLOR_GRAY2BGR)

    signals = []
    notes = []

    h, w = gray.shape

    # --- Signal 1: ELA uniformity skew (splicing evidence) ---
    try:
        ela = _ela_analysis(gray, q=75)
        ela_mean = float(ela.mean())
        ela_std = float(ela.std())
        # Uniform, low-noise documents have tight, low ELA. A spliced region
        # raises std disproportionately.
        uniformity_metric = min(100.0, (ela_std / (ela_mean + 1e-6)) * 12.0)
        label = ("high" if uniformity_metric >= 65 else
                 "suspicious" if uniformity_metric >= 40 else "ok")
        signals.append(TamperSignal(
            "compression_noise_skew", uniformity_metric, label,
            "Heuristic ELA: uneven compression noise suggests possible "
            "splicing / copy-paste."
            if label != "ok" else "Compression noise is broadly uniform."))
    except Exception:  # noqa: BLE001
        notes.append("ELA analysis skipped (image could not be recompressed).")

    # --- Signal 2: photo-page edge / region uniformity ---
    try:
        # Examine the top ~32% (photos typically live here) vs the rest.
        band = min(h // 3, 200)
        top = color[0:band]
        bottom = color[band:band + band] if h > band * 2 else color[band:h]
        if bottom.size and top.size:
            top_var = float(top.std())
            bottom_var = float(bottom.std())
            region_metric = min(100.0, abs(top_var - bottom_var) / (top_var + 1e-6) * 55.0)
            label = ("high" if region_metric >= 70 else
                     "suspicious" if region_metric >= 45 else "ok")
            signals.append(TamperSignal(
                "regional_structure_skew", region_metric, label,
                "Heuristic regional analysis indicates inconsistent image "
                "structure between the photo band and the data band."
                if label != "ok" else "Regional structure appears consistent."))
    except Exception:  # noqa: BLE001
        notes.append("Regional analysis skipped.")

    # --- Signal 3: obvious blank / invalid region ---
    if w < 50 or h < 50:
        signals.append(TamperSignal("tiny_image", 60, "suspicious",
                                    "Image resolution is too low for reliable "
                                    "document authenticity analysis."))

    # --- Signal 4: EXIF / metadata tampering hint (if provided) ---
    if metadata is not None:
        # If a real document photo, EXIF presence isn't inherently suspicious;
        # but consistency of software tags can be a soft signal. Real file
        # forensics would clone the image. We only note it as a soft signal.
        exif_detected = metadata.get("has_exif", False)
        if exif_detected:
            signals.append(TamperSignal("exif_metadata", 15, "ok",
                                        "Image carries EXIF metadata; not "
                                        "conclusive on its own."))

    # Overall
    if signals:
        overall = float(np.mean([s.score for s in signals]))
        # Weight the strongest signal slightly more
        peak = max(s.score for s in signals)
        overall = 0.6 * overall + 0.4 * peak
    else:
        overall = 0.0

    overall = round(min(100.0, overall), 1)
    risk_level = ("high" if overall >= 70 else
                  "medium" if overall >= 40 else "low")

    notes.append("Authenticity result is HEURISTIC (image-signal based), not "
                 "forensic-grade. A low score does not guarantee authenticity.")
    return TamperResult(overall_score=overall, risk_level=risk_level,
                        signals=signals, notes=notes)
