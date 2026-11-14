"""Small spatial overview tables; individual fields are never loaded for an overview."""

from sqlalchemy import JSON, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MapCell(Base):
    __tablename__ = "field_map_cells"

    level: Mapped[int] = mapped_column(primary_key=True)
    x: Mapped[int] = mapped_column(primary_key=True)
    y: Mapped[int] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column()
    area: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    min_lat: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)


class MapDataset(Base):
    __tablename__ = "map_datasets"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON)
