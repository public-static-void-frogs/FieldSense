from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    auth_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    settings: Mapped["UserSettings"] = relationship(cascade="all, delete-orphan", uselist=False)


class UserSettings(Base):
    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint("session_lifetime_hours BETWEEN 1 AND 720", name="valid_session_lifetime"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="valid_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="valid_longitude"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="paired_coordinates"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    farm_name: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(200), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    season: Mapped[str] = mapped_column(String(4), default="2026")
    time_zone: Mapped[str] = mapped_column(String(100), default="Europe/Kyiv")
    units: Mapped[str] = mapped_column(String(10), default="metric")
    theme: Mapped[str] = mapped_column(String(10), default="light")
    language: Mapped[str] = mapped_column(String(2), default="en")
    session_lifetime_hours: Mapped[int] = mapped_column(default=24)


class UserRepository:
    def __init__(self, session: Session):
        self.session = session

    def by_email(self, email: str):
        return self.session.scalar(select(User).where(User.email == email))

    def by_id(self, user_id: str):
        return self.session.get(User, user_id)
