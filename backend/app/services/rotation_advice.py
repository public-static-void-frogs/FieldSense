"""Rotation advice for a field: adapts stored fields to the standalone rule engine.

The engine (`rule_engine/` at the repository root) ranks candidate crops for the coming season
from crop history, soil, season summaries and reference tables. This module only gathers the
field's inputs and picks the crop to assess; it adds no agronomic logic of its own.

Inputs, all optional (what is missing is reported by the engine as data gaps):
    <data root>/season_summary/<year>/<county>.parquet  weather and drought per field and season
    <data root>/climate_record/                         weekly weather per grid node, 30 years
    <data root>/fields.jsonl                            soil block of the sampled fields
    <data root>/soil_points.csv, soil_units.csv         the same for a large sample (field -> map unit)
    <data root>/soil_extra.csv                          productivity indexes per map unit
    <data root>/summary_index.parquet                   sampled field of each weather cell and county
    <data root>/cdl_history_all.parquet                 CDL crop history of every CSB field
    M3 output folder (see season_timing.py)             local sowing windows, heat and frost risk
CDL labels are satellite estimates, not farmer declarations.
"""

import csv
import json
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from statistics import median

from app.services.economics import defaults as economics_defaults
from app.services.economics import engine_economics
from app.services.rotation_plan import DEFAULT_SEASONS, rotation_plan
from app.services.season_timing import local_calendar

REPO = Path(__file__).resolve().parents[3]
ACRE_TO_HA = 0.40468564224
SOIL_TIMEOUT_SECONDS = 8.0
SOIL_CACHE_SIZE = 512
SOIL_SOURCE = "USDA NRCS SSURGO via Soil Data Access (map-unit estimate)"
# survey value -> soil property the engine and the planner read; the rest is stored only
SURVEY_SOIL_KEYS = {"ph": "ph", "organicMatterPct": "om_pct"}
SURVEY_USED_IN = {
    "ph": ["rules"],
    "organicMatterPct": ["soil_carbon"],
    "phosphorusPpm": ["fertilizer_cost"],
    "potassiumPpm": ["fertilizer_cost"],
}
SURVEY_NOT_VALUES = ("sampledOn", "phosphorusTest", "potassiumSample")
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
        self._field_unit: dict[str, str] = {}  # CSBID -> mukey
        self._unit_soil: dict[str, dict] = {}  # mukey -> soil block
        self._state_aws: dict[str, float] = {}
        self._soil_cache: OrderedDict[str, dict | None] = OrderedDict()
        self._history_db = None
        self._cells = None

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
                self._load_sample()
            if source_id in self._sample_soil:
                return self._sample_soil[source_id]
            return self._unit_soil.get(self._field_unit.get(source_id, ""))

    def _load_sample(self) -> None:
        self._sample_soil = {}
        by_state: dict[str, list[float]] = {}
        extra = self._soil_extra()
        path = self._path("fields.jsonl")
        if path:
            with path.open() as handle:
                for line in handle:
                    record = json.loads(line)
                    soil = record.get("soil")
                    if not soil:
                        continue
                    soil.update(extra.get(str(soil.get("mukey")), {}))
                    self._sample_soil[record["sourceId"]] = soil
                    if soil.get("aws_100cm_mm") is not None and record.get("stateFips"):
                        by_state.setdefault(record["stateFips"], []).append(soil["aws_100cm_mm"])
        if not path:
            self._load_soil_tables(extra, by_state)
        self._state_aws = {state: median(values) for state, values in by_state.items()}

    def _load_soil_tables(self, extra: dict[str, dict], by_state: dict[str, list[float]]) -> None:
        """Soil of a large sample: soil_points.csv (CSBID, mukey) and soil_units.csv (SDA columns).

        Kept as field -> map unit -> soil, because a soil block per field does not fit in memory.
        """
        points, units = self._path("soil_points.csv"), self._path("soil_units.csv")
        if not points or not units:
            return
        if str(REPO) not in sys.path:  # called under the lock, so not through self.advisor
            sys.path.insert(0, str(REPO))
        from rule_engine.ssurgo import COLUMNS

        with units.open(newline="") as handle:
            for row in csv.DictReader(handle):
                soil = {"source": SOIL_SOURCE}
                for column, (key, convert) in COLUMNS.items():
                    if row.get(column):  # empty where the survey has no value
                        soil[key] = (
                            convert(float(row[column])) if convert is int else convert(row[column])
                        )
                soil.update(extra.get(soil.get("mukey", ""), {}))
                if len(soil) > 2:
                    self._unit_soil[soil["mukey"]] = soil
        with points.open(newline="") as handle:
            for row in csv.DictReader(handle):
                soil = self._unit_soil.get(row["mukey"])
                if soil is None:
                    continue
                self._field_unit[row["CSBID"]] = row["mukey"]
                if soil.get("aws_100cm_mm") is not None:
                    by_state.setdefault(row["CSBID"][:2], []).append(soil["aws_100cm_mm"])

    def _summary_twin(self, record: dict) -> dict | None:
        """The sampled field whose season summaries this field reads (rule_engine.cells)."""
        _ = self.advisor  # puts the rule engine on the import path
        with self._lock:
            if self._cells is None:
                from rule_engine.cells import CellIndex

                self._cells = CellIndex(self._path("summary_index.parquet"))
            twin = self._cells.twin(
                record.get("sourceId"),
                record.get("countyFips"),
                record.get("longitude"),
                record.get("latitude"),
            )
        if twin is None:
            return None
        return {
            "sourceId": twin.csbid,
            "countyFips": twin.county_fips,
            "source": twin.source,
            "distanceKm": twin.distance_km,
        }

    def _soil_extra(self) -> dict[str, dict]:
        """{mukey: productivity indexes and restriction depth} from the sample's soil_extra.csv."""
        path = self._path("soil_extra.csv")
        if path is None:
            return {}
        keys = (
            "nccpi_all",
            "nccpi_corn",
            "nccpi_soy",
            "nccpi_small_grains",
            "restriction_depth_cm",
        )
        with path.open(newline="") as handle:
            return {
                row["mukey"]: {k: float(row[k]) for k in keys if row.get(k)}
                for row in csv.DictReader(handle)
            }

    def _reference_aws(self, state_fips: str | None) -> float | None:
        """Median water storage of the sampled fields in the state, to compare this field with."""
        with self._lock:
            if self._sample_soil is None:
                self._load_sample()
            return self._state_aws.get(state_fips or "")

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
        record["summaryTwin"] = self._summary_twin(record)
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

    def advise(
        self,
        field: dict,
        crop: str | None,
        priorities: list[str],
        units: str,
        survey: dict | None = None,
        seasons: int = DEFAULT_SEASONS,
        results: list[dict] | None = None,
        economics: dict | None = None,
    ) -> dict:
        advisor = self.advisor
        record = self.engine_field(field)
        soil_inputs = self._apply_survey(record, survey)
        self._apply_results(record, results)
        region, _ = advisor.region_for(record)
        self._apply_economics(record, survey, economics, region)
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
        result["soilInputs"] = soil_inputs
        plan = rotation_plan(
            advisor,
            record,
            candidates,
            result["priorities"],
            seasons,
            self._path("season_summary"),
            self._reference_aws(record.get("stateFips")),
            result.get("offSeason"),
            int(result["asOf"][:4]),
        )
        self._rank_by_plan(result, plan)
        result["plan"] = plan
        return result

    def _apply_results(self, record: dict, results: list[dict] | None) -> None:
        """The farmer's past seasons: the crop replaces the CDL label, the yield sets the level."""
        crops = self.advisor.catalog.crops
        declared, yields = {}, {}
        for item in results or []:
            if item["crop"] not in crops:
                continue
            declared[item["year"]] = item["crop"]
            if item.get("yieldPerAcre"):
                yields.setdefault(item["crop"], {})[item["year"]] = item["yieldPerAcre"]
        if declared:
            record["declaredHistory"] = declared
        if yields:
            record["ownYields"] = yields

    def economics_defaults(self, field: dict) -> dict:
        """USDA average price, cost and rent for the field's candidate crops."""
        advisor = self.advisor
        record = self.engine_field(field)
        region, _ = advisor.region_for(record)
        return economics_defaults(advisor, record, advisor.candidate_ids(region))

    @staticmethod
    def _apply_economics(record: dict, survey: dict | None, economics: dict | None, region) -> None:
        """The farmer's prices, costs and rent, and the fertilizer change of the soil test."""
        from rule_engine.planner.nutrients import cost_changes, soil_test_effect

        survey = survey or {}
        effects = soil_test_effect(
            {
                "phosphorus": {
                    "ppm": survey.get("phosphorusPpm"),
                    "test": survey.get("phosphorusTest"),
                },
                "potassium": {
                    "ppm": survey.get("potassiumPpm"),
                    "test": survey.get("potassiumSample"),
                },
            },
            region,
        )
        if effects:
            record["soilTestEffects"] = effects
        found = engine_economics(economics, cost_changes(effects))
        if found:
            record["economics"] = found

    @staticmethod
    def _apply_survey(record: dict, survey: dict | None) -> list[dict]:
        """Put the farmer's soil test over the soil survey estimate; report where each came from."""
        soil = dict(record.get("soil") or {})
        estimated = set(soil)
        inputs = []
        for name, value in (survey or {}).items():
            if value is None or name in SURVEY_NOT_VALUES:
                continue
            key = SURVEY_SOIL_KEYS.get(name)
            if key:
                soil[key] = value
                estimated.discard(key)
            inputs.append(
                {
                    "id": name,
                    "value": value,
                    "source": "survey",
                    "usedIn": SURVEY_USED_IN.get(name, []),
                }
            )
        for name, key in SURVEY_SOIL_KEYS.items():
            if key in estimated and soil[key] is not None:
                inputs.append(
                    {
                        "id": name,
                        "value": soil[key],
                        "source": "ssurgo",
                        "usedIn": SURVEY_USED_IN[name],
                    }
                )
        if soil:
            record["soil"] = soil
        return inputs

    @staticmethod
    def _rank_by_plan(result: dict, plan: dict) -> None:
        """Order the candidates by the plan (best return first), then the crops it cannot price."""
        by_crop = {c["crop"]: c for c in plan["crops"]}
        codes = {g["crop"]: g["code"] for g in plan.get("notModelled", [])}
        priced = [c for c in result["candidates"] if c["crop"] in by_crop]
        priced.sort(key=lambda c: by_crop[c["crop"]]["rank"])
        rest = [c for c in result["candidates"] if c["crop"] not in by_crop]
        for rank, item in enumerate(priced + rest, start=1):
            found = by_crop.get(item["crop"])
            item["riskRank"] = item["rank"]
            item["rank"] = rank
            item["tier"] = found["tier"] if found else "not_modelled"
            item["notModelledCode"] = None if found else codes.get(item["crop"], "not_modelled")
        result["candidates"] = priced + rest
