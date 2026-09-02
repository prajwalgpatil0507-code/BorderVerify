"""Shared FastAPI dependencies (auth, DB session, logging)."""
from __future__ import annotations

import logging
import sys

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..config import settings
from ..models.models import get_db, Officer
from .security import decode_token


LOGGING_CONFIGURED = False


def configure_logging() -> None:
    global LOGGING_CONFIGURED
    if LOGGING_CONFIGURED:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    LOGGING_CONFIGURED = True


oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


def get_current_officer(token: str = Depends(oauth2_scheme),
                        db: Session = Depends(get_db)) -> Officer:
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = payload["sub"]
    officer = db.query(Officer).filter(Officer.username == username).first()
    if not officer or not officer.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Inactive or unknown user")
    return officer


def require_admin(officer: Officer = Depends(get_current_officer)) -> Officer:
    if officer.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Admin role required")
    return officer


def log_audit(db: Session, officer_id, action: str, detail: str = "", ip: str = ""):
    from ..models.models import AuditLog
    db.add(AuditLog(officer_id=officer_id, action=action, detail=detail, ip=ip))
    db.commit()
