import logging
from typing import get_args
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.dependencies import FieldId, ParcelId, Store
from app.schemas.crop_history import CropHistory, CropLayer
from app.schemas.field_insights import M3Insights, SoilDepletion
from app.schemas.fields import (
    CreateField,
    Crop,
    CropOption,
    Field,
    FieldHistory,
    Parcel,
    PropertyData,
    Recommendation,
    SaveCropAreas,
)
from app.services import fields as service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["fields"])


@router.get("/fields", response_model=list[Field])
def list_fields(store: Store):
    return store.fields()


@router.get("/fields/catalog", response_model=list[Field])
def catalog(
    store: Store,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Browse shared fields available for selection by the signed-in user."""
    return store.catalog(offset, limit)


@router.get("/fields/catalog/{field_id}", response_model=Field)
def catalog_field(field_id: FieldId, store: Store):
    return store.catalog_field(field_id)


@router.post(
    "/fields",
    response_model=Field,
    status_code=201,
    responses={
        409: {"description": "Parcel ID already exists in the catalog"},
    },
)
def create_field(input: CreateField, store: Store):
    """Create a shared catalog field and select it for the caller atomically."""
    return store.create(input)


@router.post("/fields/crop-areas", response_model=list[Field])
def add_crop_areas(input: SaveCropAreas, store: Store):
    """Merge selected polygons into the caller's saved crop areas."""
    from app.services.saved_crop_areas import save_crop_areas

    return save_crop_areas(store, input.areas)


@router.put("/fields/{field_id}/selection", response_model=Field)
def select_field(field_id: FieldId, store: Store):
    """Select a catalog field for the caller; repeated selections are idempotent."""
    return store.select(field_id)


@router.get("/crops", response_model=list[CropOption])
def crops():
    return [dict(value=name, label=name) for name in get_args(Crop)]


@router.get("/parcels/{parcel_id}", response_model=Parcel)
def parcel(parcel_id: ParcelId, store: Store):
    return store.parcel(parcel_id)


@router.get("/fields/{field_id}", response_model=Field)
def field(field_id: FieldId, store: Store):
    return store.require_field(field_id)


@router.delete("/fields/{field_id}", response_model=UUID)
def delete_field(field_id: FieldId, store: Store):
    """Remove the caller's selection while preserving the shared catalog field."""
    return store.remove(field_id)


@router.get("/fields/{field_id}/properties", response_model=PropertyData)
def properties(field_id: FieldId, store: Store):
    return service.properties(store.require_field(field_id))


@router.get(
    "/fields/{field_id}/history", response_model=FieldHistory, response_model_exclude_unset=True
)
def history(field_id: FieldId, store: Store):
    return service.history(store, field_id)


@router.get("/fields/{field_id}/recommendation", response_model=Recommendation)
def recommendation(field_id: FieldId, store: Store):
    return service.recommendation(store, field_id)


@router.get("/fields/{field_id}/crop-history", response_model=CropHistory)
def crop_history(
    field_id: FieldId,
    store: Store,
    part: int = Query(default=0, ge=0),
    lon: float | None = Query(default=None, ge=-180, le=180),
    lat: float | None = Query(default=None, ge=-90, le=90),
):
    from app.services.crop_history import history

    field = store.require_field(field_id)
    if (lon is None) != (lat is None):
        raise HTTPException(422, "Provide longitude and latitude together")
    return history(field, part, (lon, lat) if lon is not None else None)


@router.get("/fields/{field_id}/crop-history/layer/{year}", response_model=CropLayer)
def crop_history_layer(
    field_id: FieldId, store: Store, year: int, part: int = Query(default=0, ge=0)
):
    from app.services.crop_history import FIRST_YEAR, LAST_YEAR, layer

    field = store.require_field(field_id)
    if not FIRST_YEAR <= year <= LAST_YEAR:
        raise HTTPException(422, "Crop layer year is outside the available range")
    return layer(field, part, year)


@router.get("/fields/{field_id}/soil-depletion", response_model=SoilDepletion)
def soil_depletion(field_id: FieldId, store: Store, request: Request, part: int = Query(0, ge=0)):
    """Calculate or read the soil screening index at the selected parcel's reference point."""
    from app.services.crop_history import analysis_point

    coordinates = analysis_point(store.require_field(field_id), part)
    return request.app.state.soil_assessments.get(coordinates)


@router.get("/fields/{field_id}/m3-insights", response_model=M3Insights)
def m3_insights(field_id: FieldId, store: Store, request: Request):
    """Read precomputed crop timing and climate risks for the saved field coordinates."""
    lon, lat = store.require_field(field_id)["geometry"]["coordinates"]
    try:
        return request.app.state.m3_advice.lookup(lat, lon, include_delay_scan=True)
    except ImportError as error:
        logger.exception("M3 dependencies unavailable. Install backend/requirements.txt.")
        raise HTTPException(503, "Crop timing and risk data is temporarily unavailable") from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        logger.exception("Could not read the M3 model output")
        raise HTTPException(503, "Crop timing and risk data is temporarily unavailable") from error
