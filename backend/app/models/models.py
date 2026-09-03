"""Database models (SQLAlchemy 2.x ORM).

Synthetic/demo data only - never store real personal identity information.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (String, Integer, Float, Boolean, DateTime, Text,
                        ForeignKey, JSON, create_engine)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

from ..config import settings


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Officers / users
# ---------------------------------------------------------------------------

class Officer(Base):
    __tablename__ = "officers"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(40), default="officer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VerificationSession(Base):
    __tablename__ = "verification_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("officers.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="in_progress")  # completed | in_progress

    # Passenger / document summary
    passenger_name: Mapped[str] = mapped_column(String(200), default="")
    document_number: Mapped[str] = mapped_column(String(64), index=True, default="")
    document_type: Mapped[str] = mapped_column(String(40), default="passport")
    nationality: Mapped[str] = mapped_column(String(10), default="")
    date_of_birth: Mapped[str] = mapped_column(String(20), default="")
    sex: Mapped[str] = mapped_column(String(4), default="")

    # Results
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(20), default="LOW")
    decision: Mapped[str] = mapped_column(String(40), default="VERIFIED")

    # File reference
    image_filename: Mapped[str] = mapped_column(String(255), default="")
    reference_photo_filename: Mapped[str] = mapped_column(String(255), default="")

    # Verification method (upload | live_camera | demo | synthetic)
    method: Mapped[str] = mapped_column(String(30), default="upload")

    # Full structured result (JSON snapshot for audit / display)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    alerts: Mapped[list["Alert"]] = relationship(back_populates="session",
                                                 cascade="all, delete-orphan")

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "method": self.method,
            "passenger_name": self.passenger_name,
            "document_number": self.document_number,
            "document_type": self.document_type,
            "nationality": self.nationality,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "decision": self.decision,
            "verification_status": (self.result_json or {}).get("verification_status", ""),
            "image_url": (self.result_json or {}).get("image_url")
                         or (f"/media/uploads/{self.image_filename}" if self.image_filename else ""),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("verification_sessions.id"),
                                                   nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["VerificationSession"] = relationship(back_populates="alerts")


class WatchlistRecord(Base):
    __tablename__ = "watchlist_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    surname: Mapped[str] = mapped_column(String(120), default="")
    date_of_birth: Mapped[str] = mapped_column(String(20), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="watchlist")
    source: Mapped[str] = mapped_column(String(40), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdentityMatch(Base):
    __tablename__ = "identity_matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("verification_sessions.id"),
                                                   nullable=True)
    matched_document_number: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    officer_id: Mapped[int | None] = mapped_column(ForeignKey("officers.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# SIH DEMO DATABASE - simulated external data sources
#
# These tables model the *reference data* a real border / immigration system
# would query from external agencies (watchlist, visa registry, travel history,
# stolen-lost document register).  EVERY record is synthetic and is tagged with
# source="DEMO".  This is NOT a real government database; it exists purely so the
# prototype can demonstrate the end-to-end look-up flow offline.
# ---------------------------------------------------------------------------


class DemoMeta(Base):
    """One-row-per-key metadata describing the DEMO dataset itself."""
    __tablename__ = "demo_metadata"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    value: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                                 onupdate=datetime.utcnow)


class VisaRecord(Base):
    """Simulated visa registry - what a border system checks before admission."""
    __tablename__ = "visa_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    visa_number: Mapped[str] = mapped_column(String(64), default="")
    visa_type: Mapped[str] = mapped_column(String(30), default="")
    issuing_country: Mapped[str] = mapped_column(String(10), default="")
    issue_date: Mapped[str] = mapped_column(String(20), default="")    # YYMMDD
    expiry_date: Mapped[str] = mapped_column(String(20), default="")   # YYMMDD
    status: Mapped[str] = mapped_column(String(20), default="valid")   # valid | expired | revoked
    source: Mapped[str] = mapped_column(String(40), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TravelRecord(Base):
    """Simulated arrival/departure event history (immigration movement log)."""
    __tablename__ = "travel_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(20), default="")    # arrival | departure
    port_code: Mapped[str] = mapped_column(String(20), default="")
    country: Mapped[str] = mapped_column(String(10), default="")
    timestamp: Mapped[str] = mapped_column(String(20), default="")     # YYMMDDHHMM
    source: Mapped[str] = mapped_column(String(30), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StolenLostDocument(Base):
    """Simulated Stolen & Lost Travel Document (SLTD) register."""
    __tablename__ = "stolen_lost_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    document_type: Mapped[str] = mapped_column(String(30), default="passport")
    status: Mapped[str] = mapped_column(String(20), default="STOLEN")  # STOLEN | LOST
    reported_date: Mapped[str] = mapped_column(String(20), default="")
    issuing_country: Mapped[str] = mapped_column(String(10), default="")
    source: Mapped[str] = mapped_column(String(30), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PassportRecord(Base):
    """Simulated issued-passport registry (document-of-issue look-up).

    A real border system validates that a presented document number exists and
    is in a valid state.  This table models that look-up with demo data.
    """
    __tablename__ = "passport_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    surname: Mapped[str] = mapped_column(String(120), default="")
    given_names: Mapped[str] = mapped_column(String(120), default="")
    date_of_birth: Mapped[str] = mapped_column(String(20), default="")
    nationality: Mapped[str] = mapped_column(String(10), default="")
    date_of_issue: Mapped[str] = mapped_column(String(20), default="")
    date_of_expiry: Mapped[str] = mapped_column(String(20), default="")
    issuing_country: Mapped[str] = mapped_column(String(10), default="")
    status: Mapped[str] = mapped_column(String(20), default="valid")  # valid | revoked
    source: Mapped[str] = mapped_column(String(30), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdentityRecord(Base):
    """Simulated prior-traveller records used for duplicate-identity detection."""
    __tablename__ = "identity_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_number: Mapped[str] = mapped_column(String(64), index=True)
    surname: Mapped[str] = mapped_column(String(120), default="")
    given_names: Mapped[str] = mapped_column(String(120), default="")
    date_of_birth: Mapped[str] = mapped_column(String(20), default="")
    nationality: Mapped[str] = mapped_column(String(10), default="")
    source: Mapped[str] = mapped_column(String(30), default="DEMO")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

def _make_engine():
    from sqlalchemy import event
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _ensure_schema_migrations(engine) -> None:
    """Add columns introduced after the DB was first created (SQLite no-op ALTER).

    ``Base.metadata.create_all`` only creates *missing* tables, it never alters
    existing ones.  This applies the few additive columns we added late so an
    existing development DB keeps working without being dropped.
    """
    from sqlalchemy import inspect, text
    try:
        insp = inspect(engine)
        cols = {c["name"] for c in insp.get_columns("verification_sessions")}
        if "method" not in cols:
            with engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE verification_sessions ADD COLUMN method "
                    "VARCHAR(30) DEFAULT 'upload'"))
    except Exception:  # noqa: BLE001 - migrations are best-effort
        pass


def init_db() -> None:
    from ..core.security import hash_password
    from ..config import settings
    from . import models as _unused  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    _ensure_schema_migrations(engine)
    # Seed / upsert a default demo officer (credentials from config/env).
    with SessionLocal() as db:
        officer = db.query(Officer).filter(Officer.username == settings.DEMO_USERNAME).first()
        if not officer:
            db.add(Officer(username=settings.DEMO_USERNAME, name=settings.DEMO_NAME,
                           hashed_password=hash_password(settings.DEMO_PASSWORD),
                           role="officer"))
        else:
            # Refresh the password hash so an existing DB picks up config changes.
            officer.hashed_password = hash_password(settings.DEMO_PASSWORD)
            officer.name = settings.DEMO_NAME
        db.commit()
        seed_demo_metadata(db)
    return None


# Static markers that label this database as a demo dataset, not a real
# government source.  These are written whenever the DB is initialised.
DEMO_LABEL = "SIH DEMO DATABASE"
DEMO_DISCLAIMER = (
    "DEMO / MOCK DATA. This database contains ONLY fictional, synthetic "
    "travel-document records generated for the Smart India Hackathon prototype. "
    "It is NOT a real government, police, or immigration database and must not "
    "be represented as one. No real person's data is stored."
)
DEMO_META = {
    "dataset_label": {"value": DEMO_LABEL,
                      "description": "Human-readable name of this demo dataset."},
    "dataset_type": {"value": "DEMO / MOCK DATA",
                     "description": "Indicates the data is synthetic/demo only."},
    "disclaimer": {"value": DEMO_DISCLAIMER,
                   "description": "Legal/ethical disclaimer for the demo dataset."},
    "version": {"value": "1.0.0", "description": "Demo dataset schema version."},
    "is_real_data": {"value": "false",
                     "description": "Always false - this is simulated data."},
}


def seed_demo_metadata(db) -> None:
    """Ensure the DEMO label/disclaimer markers exist (idempotent)."""
    for key, payload in DEMO_META.items():
        row = db.query(DemoMeta).filter(DemoMeta.key == key).first()
        if row is None:
            db.add(DemoMeta(key=key, value=payload["value"],
                            description=payload["description"]))
    db.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
