"""Optional AI-assisted document analysis via Google Gemini.

This is an ADVISORY / diagnostic layer for BorderVerify. It runs AFTER the
deterministic verification pipeline and attaches a single ``ai_assist`` block to
the result. It deliberately does NOT alter any existing signal:

  * it never changes OCR, MRZ, cross-validation, tamper, face, watchlist,
    duplicate, passport/visa or risk results;
  * it never gates the final decision.

If the API key is absent, the model call fails, times out, or the model returns
nothing usable, the layer degrades to ``available: false`` and the verification
result is returned unchanged, so the existing pipeline can never be blocked by
Gemini.

Security
--------
* The API key is read ONLY from the environment (``settings.GEMINI_API_KEY``,
  which ``config.py`` populates from ``.env`` via ``python-dotenv``). It is never
  hardcoded in this module.
* The key is never returned to the frontend: ``analyze_document`` returns only
  plain-text analysis fields, no credentials.
"""
from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Optional

from ..config import settings

# Default model used when GEMINI_MODEL is not set (configurable via env).
# Kept in sync with config.Settings.GEMINI_MODEL default.
_DEFAULT_MODEL = "gemini-3.6-flash"


def is_configured() -> bool:
    """Return True only when a Gemini API key is present in the environment."""
    return bool((settings.GEMINI_API_KEY or "").strip())


def _mime_type(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "image/png"


def _unavailable(reason: str, status: str = "unavailable") -> dict:
    return {
        "available": False,
        "status": status,
        "reason": reason,
        "model": None,
        "summary": None,
        "observations": [],
        "flagged_fields": [],
        "risk_hint": "unknown",
        "confidence": None,
    }


def disabled_payload(reason: str) -> dict:
    """A no-call payload for scenarios that must NOT hit Gemini (e.g. demo)."""
    return _unavailable(reason, status="skipped")


def unavailable_payload(reason: str, status: str = "unavailable") -> dict:
    """Public fallback payload for the orchestrator (timeout / failure)."""
    return _unavailable(reason, status=status)


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    mod = type(exc).__module__.lower()
    return ("timeout" in name or "timeout" in mod
            or isinstance(exc, TimeoutError))


def _status_code(exc: Exception):
    return getattr(exc, "code", None) or getattr(exc, "status_code", None)


def _friendly_reason(exc: Exception, timeout_s: float) -> str:
    """Map common Gemini failures to an actionable, short reason."""
    if _is_timeout(exc):
        return f"AI-assisted analysis timed out after {timeout_s:.0f}s."
    code = _status_code(exc)
    if code == 429:
        return "Gemini rate-limited (429); AI analysis unavailable."
    if code == 503:
        return "Gemini unavailable (503); AI analysis unavailable."
    if code == 404:
        return "Gemini model not found; AI analysis unavailable."
    if code == 403:
        return "Gemini API key rejected (403); AI analysis unavailable."
    # Prefer the API's own status string where available.
    status_text = getattr(exc, "__str__", lambda: "")()
    if "429" in status_text:
        return "Gemini rate-limited (429); AI analysis unavailable."
    if "503" in status_text:
        return "Gemini unavailable (503); AI analysis unavailable."
    return f"Gemini request failed: {type(exc).__name__}: {status_text}"


_PROMPT = (
    "You are assisting a border-control document verification system. Analyze "
    "the provided identity document image and the OCR text that was extracted "
    "from it. Return ONLY a JSON object - no prose and no markdown fences - with "
    "exactly these keys:\n"
    '{\"document_type\": \"...\", \"summary\": \"...\", '
    '\"observations\": [\"...\"], '
    '\"flagged_fields\": [{\"field\": \"...\", \"reason\": \"...\", '
    '\"severity\": \"low|medium|high\"}], '
    '\"risk_hint\": \"low|medium|high|unknown\", \"confidence\": 0.0}\n'
    "If the document appears legitimate, describe the observed document type and "
    "put matching legitimate observations without flagging anything. If anything "
    "looks inconsistent, doctored, unusually low quality, or mismatched versus "
    "the supplied OCR text, record it in flagged_fields with a severity of "
    "high/medium/low and a concrete reason. Be conservative: only flag visually "
    "or semantically clear issues.\n"
)


def _extract_json(text: str) -> Optional[dict]:
    """Parse a (possibly markdown-fenced) JSON object from model output."""
    if not text:
        return None
    cleaned = text.strip()
    # Strip ```json ... ``` (or plain ```) fences if the model wrapped the object.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        # Fall back to the first {...} block if the model added surrounding text.
        block = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if block:
            try:
                data = json.loads(block.group(0))
                return data if isinstance(data, dict) else None
            except (ValueError, TypeError):
                return None
        return None


def _normalize(data: dict) -> dict:
    """Coerce model output into a stable shape, defaulting missing keys."""
    flagged = data.get("flagged_fields") or []
    if not isinstance(flagged, list):
        flagged = []
    observations = data.get("observations") or []
    if not isinstance(observations, list):
        observations = []
    confidence = data.get("confidence")
    try:
        confidence = round(float(confidence), 3) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    risk_hint = str(data.get("risk_hint", "unknown")).lower()
    if risk_hint not in ("low", "medium", "high", "unknown"):
        risk_hint = "unknown"
    return {
        "document_type": data.get("document_type") or None,
        "summary": data.get("summary") or None,
        "observations": [str(o) for o in observations][:10],
        "flagged_fields": [
            {
                "field": str(f.get("field", "unknown")) if isinstance(f, dict) else str(f),
                "reason": str(f.get("reason", "")) if isinstance(f, dict) else "",
                "severity": (str(f.get("severity", "medium")).lower()
                             if isinstance(f, dict) else "medium"),
            }
            for f in flagged[:10]
        ],
        "risk_hint": risk_hint,
        "confidence": confidence,
    }


def _context_block(ocr_text: str, fields: dict, document_type: str) -> str:
    return (
        f"Document type: {document_type}\n\n"
        f"OCR text:\n{(ocr_text or '')[:8000]}\n\n"
        f"Extracted fields:\n{json.dumps(fields or {}, indent=2, default=str)[:3000]}\n\n"
        f"{_PROMPT}"
    )


def analyze_document(image_path: str,
                     ocr_text: str,
                     fields: dict,
                     document_type: str = "auto") -> dict:
    """Run advisory Gemini analysis. Never raises; returns a dict on any outcome.

    ``ocr_text`` / ``fields`` come from the existing OCR/MRZ extraction. If a
    readable image is available it is attached alongside the text; otherwise the
    analysis falls back to the text context alone. Any failure returns the
    ``available: False`` payload so the caller can continue normally.
    """
    if not is_configured():
        return _unavailable("GEMINI_API_KEY is not set; AI-assisted layer is disabled.")

    model = settings.GEMINI_MODEL or _DEFAULT_MODEL
    timeout_s = max(1.0, float(getattr(settings, "GEMINI_TIMEOUT_S", 6) or 6))

    try:
        # Imported lazily so the rest of the app never depends on the SDK being
        # present. If it is missing the try/except degrades gracefully.
        from google import genai
        from google.genai import types

        # Strict HTTP timeout: a slow / busy / hanging Gemini call raises and is
        # caught below, so it can never block the verification pipeline.
        client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=timeout_s),
        )

        contents = []
        if image_path and Path(image_path).exists():
            try:
                data = Path(image_path).read_bytes()
                contents.append(types.Part.from_bytes(
                    data=data, mime_type=_mime_type(image_path)))
            except Exception:  # noqa: BLE001 - unreadable image -> text-only
                contents = []
        contents.append(_context_block(ocr_text, fields, document_type))

        resp = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )

        data = _extract_json(getattr(resp, "text", None) or "")
        if not data:
            return _unavailable("Model returned no usable JSON response.")
        return {
            "available": True,
            "status": "ok",
            "reason": None,
            "model": model,
            **_normalize(data),
        }
    except Exception as exc:  # noqa: BLE001 - never let Gemini block verification
        return _unavailable(_friendly_reason(exc, timeout_s))
