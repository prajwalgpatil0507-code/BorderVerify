"""Authentication routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..core.deps import log_audit
from ..core.security import create_access_token, verify_password
from ..config import settings
from ..models.models import get_db, Officer
from ..schemas.schemas import Token

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(),
          db: Session = Depends(get_db)):
    officer = db.query(Officer).filter(Officer.username == form.username).first()
    if not officer or not verify_password(form.password, officer.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not officer.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Account is disabled")
    token = create_access_token(officer.username, officer.role)
    log_audit(db, officer.id, "login", "Officer logged in")
    return Token(access_token=token, username=officer.username, role=officer.role)
