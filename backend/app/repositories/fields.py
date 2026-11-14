"""Shared field catalog and account-scoped selections stored in SQL."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.core.errors import ResourceConflict, ResourceNotFound
from app.schemas.fields import CreateField


class FieldRecord(Base):
    __tablename__ = "fields"
    __table_args__ = (
        CheckConstraint("area > 0", name="positive_field_area"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="valid_field_longitude"),
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="valid_field_latitude"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    parcel_id: Mapped[int | None] = mapped_column(unique=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE", name="fk_field_owner")
    )
    boundary: Mapped[dict | None] = mapped_column(JSON)
    crop: Mapped[str | None] = mapped_column(String(30))
    area: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    latitude: Mapped[float] = mapped_column(Float)
    # Optional supplied attributes are kept together; absent measurements stay absent.
    attributes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source_id: Mapped[str | None] = mapped_column(String(32), unique=True)
    location_kind: Mapped[str] = mapped_column(String(24), default="user_point")
    state_fips: Mapped[str | None] = mapped_column(String(2))
    county_fips: Mapped[str | None] = mapped_column(String(3))
    county: Mapped[str | None] = mapped_column(String(80))


Index(
    "uq_field_owner_crop",
    FieldRecord.owner_id,
    FieldRecord.crop,
    unique=True,
    postgresql_where=text("owner_id IS NOT NULL"),
    sqlite_where=text("owner_id IS NOT NULL"),
)


Index(
    "ix_fields_spatial",
    func.point(FieldRecord.longitude, FieldRecord.latitude),
    postgresql_using="gist",
).ddl_if(dialect="postgresql")


class UserField(Base):
    __tablename__ = "user_fields"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    field_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fields.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PendingFieldSelection(Base):
    """Selection recovery across a catalog replacement; restored after matching points load."""

    __tablename__ = "pending_field_selections"
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    field_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def field_view(row: FieldRecord):
    attributes = {
        "properties": None,
        "planted": None,
        "health": None,
        "moisture": None,
        "nitrogen": None,
        "status": None,
        **row.attributes,
    }
    return dict(
        attributes,
        id=row.id,
        parcelId=row.parcel_id,
        name=row.crop or (f"CSB {row.source_id}" if row.source_id else "Field"),
        boundary=row.boundary,
        crop=row.crop,
        area=row.area,
        geometry=dict(type="Point", coordinates=[row.longitude, row.latitude]),
        sourceId=row.source_id,
        locationKind=row.location_kind,
        sourceYear=2025 if row.source_id else None,
        county=row.county,
        stateFips=row.state_fips,
        countyFips=row.county_fips,
    )


class FieldRepository:
    def __init__(self, session: Session, user_id: str):
        self.session = session
        self.user_id = user_id

    def catalog(self, offset=0, limit=100):
        from app.services.maps import require_ready

        require_ready(self.session)
        return [
            field_view(row)
            for row in self.session.scalars(
                select(FieldRecord)
                .where(FieldRecord.owner_id.is_(None))
                .order_by(FieldRecord.id)
                .offset(offset)
                .limit(limit)
            )
        ]

    def catalog_field(self, field_id):
        from app.services.maps import require_ready

        require_ready(self.session)
        row = self.session.get(FieldRecord, str(field_id))
        if row is None or row.owner_id is not None:
            raise ResourceNotFound("Field not found")
        return field_view(row)

    def fields(self):
        rows = self.session.scalars(
            select(FieldRecord)
            .join(UserField)
            .where(UserField.user_id == self.user_id)
            .order_by(UserField.selected_at, FieldRecord.id)
        )
        return [field_view(row) for row in rows]

    def require_field(self, field_id):
        if self.session.get(UserField, (self.user_id, str(field_id))) is None:
            raise ResourceNotFound("Field not found")
        return field_view(self.session.get(FieldRecord, str(field_id)))

    def parcel(self, parcel_id):
        row = self.session.scalar(select(FieldRecord).where(FieldRecord.parcel_id == parcel_id))
        if row is None:
            raise ResourceNotFound("Parcel not found")
        soil = (row.attributes.get("properties") or {}).get("soil", {})
        return dict(
            id=parcel_id,
            name=row.crop or "Field",
            crop=row.crop,
            area=row.area,
            soilType=soil.get("soilType"),
        )

    def create(self, payload: CreateField):
        from app.services.maps import require_ready, update_cells

        require_ready(self.session)
        data = payload.model_dump(mode="json")
        longitude, latitude = data.pop("geometry")["coordinates"]
        data.pop("name", None)
        row = FieldRecord(
            parcel_id=data.pop("parcelId"),
            crop=data.pop("crop"),
            area=data.pop("area"),
            attributes=data,
            longitude=longitude,
            latitude=latitude,
        )
        self.session.add(row)
        try:
            self.session.flush()
            self.session.add(UserField(user_id=self.user_id, field_id=row.id))
            update_cells(self.session, row)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise ResourceConflict("A field with this parcel ID already exists") from error
        return field_view(row)

    def select(self, field_id):
        from app.services.maps import require_ready

        require_ready(self.session)
        fid = str(field_id)
        row = self.session.get(FieldRecord, fid)
        if row is None or row.owner_id is not None:
            raise ResourceNotFound("Field not found")
        if row.crop:
            owned = self.session.scalar(
                select(FieldRecord).where(
                    FieldRecord.owner_id == self.user_id, FieldRecord.crop == row.crop
                )
            )
            if owned is not None:
                return field_view(owned)
        if self.session.get(UserField, (self.user_id, fid)) is None:
            self.session.add(UserField(user_id=self.user_id, field_id=fid))
            try:
                self.session.commit()
            except IntegrityError:
                self.session.rollback()
                # Concurrent identical selections are still a successful PUT.
                if self.session.get(UserField, (self.user_id, fid)) is None:
                    raise
        return field_view(row)

    def remove(self, field_id):
        self.require_field(field_id)
        row = self.session.get(FieldRecord, str(field_id))
        if row.owner_id == self.user_id:
            self.session.delete(row)
        else:
            self.session.delete(self.session.get(UserField, (self.user_id, str(field_id))))
        self.session.commit()
        return str(field_id)
