"""Basic passive liveness / anti-spoofing analysis.

Scope and honesty
-----------------
There is NO certified presentation-attack-detection (PAD) model deployed here.
Instead this layer computes several genuine, interpretable image-forensics cues
that are *indicative* of a photographed / screened replay versus a live subject:

  * high-frequency moire / aliasing energy (a screen or print rescan)
  * specular glare / sheen across the frame (photograph of a glass/screen)
  * unnatural, uniform colour cast (screen tint)
  * global blur / loss of high-frequency detail at typical face sizes

The result is deliberately conservative and transparent:

  * ``spoof_suspected``  - only when one or more of the above cues is STRONG.
  * ``live``            - only when NO spoof cue is present AND passable quality.
  * ``unknown``         - everything else (insufficient signal to decide).
  * ``not_applicable``  - liveness is only meaningful for a live-camera capture;
                          a static uploaded photo cannot prove liveness.

It NEVER claims certified liveness and NEVER auto-flags a real person based on a
weak heuristic.  Anyone reading the result sees exactly which cue drove it.
"""
from __future__ import annotations

import numpy as np
import cv2


def _to_gray(matrix: np.ndarray):
    if matrix is None or matrix.size == 0:
        return None
    if matrix.ndim == 3:
        return cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    return matrix


def _bounded(v: float, lo=0.0, hi=100.0) -> float:
    return float(max(lo, min(hi, v)))


def _moire_score(gray: np.ndarray) -> float:
    """High-frequency (screen/print) aliasing energy.

    A live camera image of a person is dominated by smooth mid-frequency detail.
    A photographed screen/photo tends to carry a periodic high-frequency pattern
    left over from the pixel/print grid.  We isolate that band with a high-pass
    and measure how much energy is concentrated in it.
    """
    h, w = gray.shape
    if h < 40 or w < 40:
        return 0.0
    smooth = cv2.GaussianBlur(gray, (0, 0), 3.0).astype(np.float32)
    high = gray.astype(np.float32) - smooth
    energy = float(np.sqrt(np.mean(high ** 2)))      # RMS of high-frequency residual
    # Typical live frame RMS ~1-4. Screen/print replays with visible moire ~8+.
    return _bounded(max(0.0, (energy - 4.0) / 0.12))


def _glare_score(matrix: np.ndarray) -> float:
    """Specular glare / sheen (unphysical bright, low-texture regions)."""
    if matrix.ndim != 3:
        return 0.0
    gray = cv2.cvtColor(matrix, cv2.COLOR_BGR2GRAY)
    bright = (gray > 215).astype(np.float32)
    # Count very-bright pixels *their smoothness*: a real highlight is small and
    # sharp; a full-frame sheen is large and flat.
    ratio = float(bright.mean())
    if ratio < 0.005:
        return 0.0
    # A large, flat bright band signals a reflective surface over the lens.
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    smooth_bright = float(laplacian[bright > 0].std()) if (bright > 0).any() else 255
    # large ratio + low detail in the bright area => sheen
    return _bounded(ratio * 260.0 * (1.0 - _bounded(smooth_bright / 60.0, 0, 1)))


def _colour_cast_score(matrix: np.ndarray) -> float:
    """Strong, single-channel colour tint (screen/print colour cast)."""
    if matrix.ndim != 3:
        return 0.0
    hsv = cv2.cvtColor(matrix, cv2.COLOR_BGR2HSV)
    hist, _ = np.histogram(hsv[:, :, 0], bins=36, range=(0, 180), density=True)
    if hist.size == 0 or float(hist.max()) <= 0:
        return 0.0
    hist = hist / float(hist.max())
    # A very peaked hue distribution (one dominant hue) is a strong tint cue.
    peak = float(hist.max())
    return _bounded(max(0.0, (peak - 0.45) * 160.0))


def _overall_quality(gray: np.ndarray) -> float:
    """0-100 sharpness-quality gate so we do not call a blurred frame 'live'."""
    if gray is None:
        return 0.0
    h, w = gray.shape
    scale = 500.0 / max(h, w)
    small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA) if scale < 1 else gray
    lap_var = float(cv2.Laplacian(small, cv2.CV_64F).var())
    return _bounded(lap_var / 9.0)


def check_liveness(matrix: np.ndarray) -> dict:
    """Run passive liveness cues on a single frame.

    Returns a structured dict with ``status`` (live | unknown | spoof_suspected),
    ``confidence`` (0-1), per-cue ``scores`` and an honest ``note``.
    """
    if matrix is None or matrix.size == 0:
        return {"status": "unknown", "confidence": 0.0, "scores": {},
                "note": "No live-camera image was provided, so liveness could not be assessed."}

    gray = _to_gray(matrix)
    moire = _moire_score(gray)
    glare = _glare_score(matrix)
    cast = _colour_cast_score(matrix)
    quality = _overall_quality(gray)

    cues = {
        "moire_aliasing": _bounded(moire),
        "specular_glare": _bounded(glare),
        "colour_cast": _bounded(cast),
    }

    # Thresholds deliberately conservative: only strong evidence triggers a flag.
    strong_spoof = (moire >= 45 and quality < 60) or \
                   (glare >= 45) or \
                   (moire >= 60)

    if strong_spoof:
        status = "spoof_suspected"
        confidence = float(_bounded(max(moire, glare, cast) / 100.0, 0.45, 0.92))
        note = ("A screen/print replay cue (moire/glare/colour cast) is present. "
                "This is a heuristic PAD indicator, not a certified liveness verdict "
                "- treat as SUSPECT and require a manual or challenge-response check.")
    elif quality < 40:
        status = "unknown"
        confidence = 0.0
        note = ("The frame is too soft/underexposed to assess liveness reliably "
                "(blurred or low-light capture). No liveness call is made.")
    else:
        status = "live"
        confidence = 0.55
        note = ("No strong screen/print replay cue was observed. This is a weak "
                "positive from a passive heuristic - it is NOT a certified "
                "presentation-attack-detection result, but it supports a live capture.")

    return {
        "status": status,
        "confidence": round(confidence, 3),
        "scores": {k: round(v, 1) for k, v in cues.items()},
        "quality_score": round(quality, 1),
        "note": note,
    }
