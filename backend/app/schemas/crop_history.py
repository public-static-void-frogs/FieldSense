from pydantic import BaseModel


class CropClass(BaseModel):
    code: int
    label: str
    color: str


class CropYear(BaseModel):
    year: int
    crop: CropClass | None


class CropHistory(BaseModel):
    coordinates: tuple[float, float]
    years: list[CropYear]


class CropLayerClass(CropClass):
    share: float


class CropLayer(BaseModel):
    bounds: tuple[float, float, float, float]
    image: str | None
    classes: list[CropLayerClass]
