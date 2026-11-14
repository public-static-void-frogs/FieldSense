"""Crop catalog: CDL code -> crop -> group -> traits, loaded from crops.yaml.

A crop is a candidate in a region when crops.yaml lists the region or when state_crops.csv
(built from the national CSB crop history by data/usa_sample/state_crops.py) shows the crop
is actually grown in that state.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CATALOG = Path(__file__).resolve().parent / "data" / "crops.yaml"
STATE_CROPS = "state_crops.csv"  # region, crop, ...: next to the catalog file, optional
NON_CANDIDATE_GROUPS = frozenset({"fallow", "non_crop"})


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class Trait:
    value: Any
    verified: bool = True
    source: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class CropGroup:
    id: str
    label: str
    traits: dict[str, Trait]
    calendar: dict[str, int]


@dataclass(frozen=True)
class Crop:
    id: str
    label: str
    group: CropGroup
    cdl_codes: tuple[int, ...]
    traits: dict[str, Trait]
    regions: tuple[str, ...]
    stage_names: dict[str, str]
    display_unit: str
    bu_to_t_ha: float | None
    ton_to_t_ha: float | None = None
    components: tuple[str, ...] = ()
    calendar: dict[str, int] | None = None  # crop-level override of the group calendar
    calendar_source: str | None = None

    def trait(self, name: str) -> Trait:
        if name in self.traits:
            return self.traits[name]
        if name in self.group.traits:
            return self.group.traits[name]
        raise KeyError(f"Crop {self.id} has no trait {name}")

    def value(self, name: str, default=None):
        try:
            return self.trait(name).value
        except KeyError:
            return default

    def all_traits(self) -> dict[str, Trait]:
        return {**self.group.traits, **self.traits}


@dataclass(frozen=True)
class Catalog:
    version: str
    crops: dict[str, Crop]
    groups: dict[str, CropGroup]
    cdl_index: dict[int, Crop] = field(default_factory=dict)

    def by_cdl(self, code) -> Crop | None:
        if code is None:
            return None
        return self.cdl_index.get(int(code))

    def candidates(self, region: str) -> list[Crop]:
        return [
            crop
            for crop in self.crops.values()
            if region in crop.regions and crop.group.id not in NON_CANDIDATE_GROUPS
        ]

    def trait(self, crop: Crop, name: str) -> Trait:
        return crop.trait(name)


def _trait(raw) -> Trait:
    if isinstance(raw, dict) and "value" in raw:
        unknown = set(raw) - {"value", "verified", "source", "text"}
        if unknown:
            raise CatalogError(f"Unknown trait keys {sorted(unknown)}")
        return Trait(
            value=raw["value"],
            verified=bool(raw.get("verified", True)),
            source=raw.get("source"),
            text=raw.get("text"),
        )
    return Trait(value=raw)


def load_catalog(path: Path = DEFAULT_CATALOG) -> Catalog:
    document = yaml.safe_load(Path(path).read_text())
    groups = {}
    for group_id, raw in document["groups"].items():
        calendar = raw.get("calendar") or {}
        groups[group_id] = CropGroup(
            id=group_id,
            label=raw["label"],
            traits={name: _trait(value) for name, value in raw["traits"].items()},
            calendar={stage: int(doy) for stage, doy in calendar.items()},
        )
    grown: dict[str, list[str]] = {}
    state_crops = Path(path).parent / STATE_CROPS
    if state_crops.exists():
        with state_crops.open(newline="") as handle:
            for row in csv.DictReader(handle):
                grown.setdefault(row["crop"], []).append(row["region"])
    crops = {}
    cdl_index = {}
    for crop_id, raw in document["crops"].items():
        if raw["group"] not in groups:
            raise CatalogError(f"Crop {crop_id} references unknown group {raw['group']}")
        crop = Crop(
            id=crop_id,
            label=raw["label"],
            group=groups[raw["group"]],
            cdl_codes=tuple(int(code) for code in raw.get("cdl_codes", [])),
            traits={name: _trait(value) for name, value in (raw.get("traits") or {}).items()},
            regions=tuple(dict.fromkeys([*(raw.get("regions") or []), *grown.get(crop_id, [])])),
            stage_names=dict(raw.get("stage_names") or {}),
            display_unit=raw.get("display_unit") or "",
            bu_to_t_ha=raw.get("bu_to_t_ha"),
            ton_to_t_ha=raw.get("ton_to_t_ha"),
            components=tuple(raw.get("components") or []),
            calendar=(
                {stage: int(doy) for stage, doy in raw["calendar"]["stages"].items()}
                if raw.get("calendar")
                else None
            ),
            calendar_source=(raw.get("calendar") or {}).get("source"),
        )
        for code in crop.cdl_codes:
            if code in cdl_index:
                raise CatalogError(
                    f"CDL code {code} mapped twice ({cdl_index[code].id}, {crop_id})"
                )
            cdl_index[code] = crop
        crops[crop_id] = crop
    for crop in crops.values():
        for component in crop.components:
            if component not in crops:
                raise CatalogError(f"Crop {crop.id} has unknown component {component}")
    return Catalog(
        version=str(document["version"]), crops=crops, groups=groups, cdl_index=cdl_index
    )
