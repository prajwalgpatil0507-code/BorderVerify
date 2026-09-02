"""Pydantic schemas for request/response payloads."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str = ""
    role: str = ""


class LoginRequest(BaseModel):
    username: str
    password: str


# ---------------------------------------------------------------------------
# Upload / Verify
# ---------------------------------------------------------------------------

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    file_type: str
    size_bytes: int


class VerifyRequest(BaseModel):
    image_filename: str = Field(..., description="Uploaded document image filename")
    reference_photo_filename: Optional[str] = Field(
        None, description="Optional passport photo / live photo filename")
    document_type: str = Field("auto", description="auto | passport | visa")
    provided_photo_filename: Optional[str] = None
    # Optional manual passenger attributes (form data)
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None


class SyntheticVerifyRequest(BaseModel):
    # Trigger the synthetic-document tamper/anomaly demonstrator.
    synthetic_id: str = Field(..., description="aadhaar_valid | aadhaar_tampered | "
                                               "pan_valid | pan_tampered | "
                                               "college_valid | college_tampered")


class RawVerifyRequest(BaseModel):
    # For JSON-based verification (no image) e.g. demo cases
    document_number: Optional[str] = None
    surname: Optional[str] = None
    given_names: Optional[str] = None
    date_of_birth: Optional[str] = None
    nationality: Optional[str] = None
    sex: Optional[str] = None
    date_of_expiry: Optional[str] = None
    document_type: Optional[str] = "passport"
    mrz_lines: Optional[list[str]] = None
    scenario: Optional[str] = None    # valid | expired | mrz_mismatch | face_mismatch | tamper | watchlist | duplicate
    face_score: Optional[float] = None
    # Provide a file that holds the face image when needed
    provided_photo_filename: Optional[str] = None
