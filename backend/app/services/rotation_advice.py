"""Rotation advice for a field: adapts stored fields to the standalone rule engine.

The engine (`rule_engine/` at the repository root) ranks candidate crops for the coming season
from crop history, soil, season summaries and reference tables. This module only gathers the
field's inputs and picks the crop to assess; it adds no agronomic logic of its own.

Inputs, all optional (what is missing is reported by the engine as data gaps):
    <data root>/season_summary/<year>/<county>.parquet  weather and drought per field and season
    <data root>/climate_record/                         weekly weather per grid node, 30 years
    <data root>/fields.jsonl                            soil block of the sampled fields
    <data root>/cdl_history_all.parquet                 CDL crop history of every CSB field
    M3 output folder (see season_timing.py)             local sowing windows, heat and frost risk
CDL labels are satellite estimates, not farmer declarations.
"""

import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path

from app.services.season_timing import local_calendar

REPO = Path(__file__).resolve().parents[3]
ACRE_TO_HA = 0.40468564224
SOIL_TIMEOUT_SECONDS = 8.0
SOIL_CACHE_SIZE = 512
PRIORITIES = ("water", "soil", "erosion", "income", "pest_break")
# crop names a user can declare for a field -> engine crop ids
DECLARED_CROPS = {
    "Winter wheat": "winter_wheat",
    "Corn": "corn",
    "Soybeans": "soybeans",
    "Alfalfa": "alfalfa",
    "Grassland/Pasture": "grass_pasture",
}


class InvalidAdviceRequest(ValueError):
    """The requested crop or priorities cannot be assessed for this field."""


class RotationAdvice:
    def __init__(self, data_root: str | Path | None, soil_lookup: bool = True, timing=None):
        self.data_root = Path(data_root) if data_root else None
        self.soil_lookup = soil_lookup
        self.timing = timing  # SeasonTiming, or None
        self._lock = threading.Lock()
        self._advisor = None
        self._sample_soil: dict[str, dict] | None = None
        self._soil_cache: OrderedDict[str, dict | None] = OrderedDict()
        self._history_db = None

    # -- engine and data files ---------------------------------------------------------

    def _path(self, name: str) -> Path | None:
        path = self.data_root / name if self.data_root else None
        return path if path is not None and path.exists() else None

    @property
    def advisor(self):
        with self._lock:
            if self._advisor is None:
                try:
                    from rule_engine import build_advisor
                except ModuleNotFoundError:
                    sys.path.insert(0, str(REPO))
                    from rule_engine import build_advisor
                self._advisor = build_advisor(
                    self._path("season_summary"), climate_root=self._path("climate_record")
                )
            return self._advisor

    def _sampled_soil(self, source_id: str) -> dict | None:
        with self._lock:
            if self._sample_soil is None:
                self._sample_soil = {}
                path = self._path("fields.jsonl")
                if path:
                    with path.open() as handle:
                        for line in handle:
                            record = json.loads(line)
                            if record.get("soil"):
                                self._sample_soil[record["sourceId"]] = record["soil"]
            return self._sample_soil.get(source_id)

    def _cdl_history(self, source_id: str) -> dict[str, int]:
        path = self._path("cdl_history_all.parquet")
        if path is None:
            return {}
        import duckdb

        with self._lock:
            if self._history_db is None:
                self._history_db = duckdb.connect()
            cursor = self._history_db.cursor()
        result = cursor.execute(
            "SELECT * FROM read_parquet(?) WHERE CSBID = ?", [str(path), source_id]
        )
        names = [column[0] for column in result.description]
        row = result.fetchone()
        if row is None:
            return {}
        return {
            name: int(value)
            for name, value in zip(names, row, strict=True)
            if name.startswith("CDL") and value is not None
        }

    def _soil(self, field: dict) -> dict | None:
        source_id = field.get("sourceId")
        if source_id and (soil := self._sampled_soil(source_id)):
            return soil
        if not self.soil_lookup:
            return None
        key = field["id"]
        with self._lock:
            if key in self._soil_cache:
                self._soil_cache.move_to_end(key)
                return self._soil_cache[key]
        try:
            from rule_engine.ssurgo import fetch_soil

            longitude, latitude = field["geometry"]["coordinates"]
            soil = fetch_soil(latitude, longitude, timeout=SOIL_TIMEOUT_SECONDS)
        except (OSError, ValueError, KeyError):
            return None  # not cached: the soil service may answer next time
        with self._lock:
            self._soil_cache[key] = soil
            while len(self._soil_cache) > SOIL_CACHE_SIZE:
                self._soil_cache.popitem(last=False)
        return soil

    # -- field adaptation --------------------------------------------------------------

    def engine_field(self, field: dict) -> dict:
        """The stored field in the shape the rule engine reads."""
        state, county = field.get("stateFips"), field.get("countyFips")
        source_id = field.get("sourceId")
        properties = dict(field.get("sourceProperties") or {})
        if source_id and not any(key.startswith("CDL") for key in properties):
            properties.update(self._cdl_history(source_id))
        record = {
            "id": str(field["id"]),
            "crop": field.get("crop"),
            "area": field["area"],  # hectares
            "sourceId": source_id,
            "stateFips": state,
            "countyFips": f"{state}{county}" if state and county else None,
            "sourceYear": field.get("sourceYear"),
            "sourceProperties": properties,
        }
        try:
            record["longitude"], record["latitude"] = field["geometry"]["coordinates"]
        except (KeyError, TypeError, ValueError):
            pass  # the engine then takes the position from the field's season summaries
        soil = self._soil(field)
        if soil:
            record["soil"] = soil
        return {key: value for key, value in record.items() if value is not None}

    def _intended(self, record: dict, candidates: list[str]) -> tuple[str, str]:
        declared = DECLARED_CROPS.get(record.get("crop") or "")
        if declared in candidates:
            return declared, "field_crop"
        properties = record.get("sourceProperties", {})
        for key in sorted((k for k in properties if k.startswith("CDL")), reverse=True):
            crop = self.advisor.catalog.by_cdl(properties[key])
            if crop and crop.id in candidates:
                return crop.id, "history"
        return candidates[0], "default"

    # -- public ------------------------------------------------------------------------

    def advise(self, field: dict, crop: str | None, priorities: list[str], units: str) -> dict:
        advisor = self.advisor
        record = self.engine_field(field)
        region, _ = advisor.region_for(record)
        candidates = advisor.candidate_ids(region)
        if crop is None:
            crop, source = self._intended(record, candidates)
        elif crop in candidates:
            source = "requested"
        else:
            raise InvalidAdviceRequest(f"Crop '{crop}' is not a candidate crop for this field")
        unknown = sorted(set(priorities) - set(PRIORITIES))
        if unknown:
            raise InvalidAdviceRequest(f"Unknown priorities: {', '.join(unknown)}")
        timing = self.timing.for_field(field) if self.timing else None
        local = local_calendar(timing)
        if local:
            record["stageCalendar"] = local  # local sowing dates move the hazard windows
        result = advisor.advise(record, crop, list(dict.fromkeys(priorities)), units)
        result["intendedCropSource"] = source
        result["cropOptions"] = [
            {
                "id": crop_id,
                "label": advisor.catalog.crops[crop_id].label,
                "group": advisor.catalog.crops[crop_id].group.id,
            }
            for crop_id in candidates
        ]
        result["areaHa"] = field["area"]
        # shown next to the ranking; only its sowing date reaches the engine (see above)
        result["seasonTiming"] = timing
        return result
