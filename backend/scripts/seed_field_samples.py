"""Explicit, reversible crop/soil samples for currently selected fields.

python scripts/seed_field_samples.py
python scripts/seed_field_samples.py --restore

Never runs during application startup or the real-source import.
"""

import argparse
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.core.database import database_engine, session_factory  # noqa: E402
from app.repositories import users  # noqa: E402, F401
from app.repositories.fields import FieldRecord, UserField  # noqa: E402
from app.repositories.maps import MapDataset  # noqa: E402
from app.schemas.fields import PropertyData  # noqa: E402

SEED_ID = "prototype-field-types"
SAMPLES = (
    ("Corn", "Silt loam", 6.5, 3.8, 182, "Well drained"),
    ("Soybeans", "Clay loam", 6.8, 3.2, 195, "Moderately well drained"),
    ("Winter wheat", "Loam", 6.4, 3.5, 170, "Well drained"),
)


def seed(session, restore=False):
    backup = session.get(MapDataset, SEED_ID, with_for_update=True)
    records = deepcopy(backup.metadata_.get("fields", {})) if backup else {}
    changed = []
    if restore:
        for field_id, record in records.items():
            field = session.get(FieldRecord, field_id, with_for_update=True)
            if field is None:
                continue
            attributes = deepcopy(field.attributes)
            # Preserve any real values supplied after the temporary sample was seeded.
            if field.crop == record["sampleCrop"]:
                field.crop = record["originalCrop"]
            if attributes.get("properties") == record["sampleProperties"]:
                if record["hadProperties"]:
                    attributes["properties"] = record["originalProperties"]
                else:
                    attributes.pop("properties", None)
            field.attributes = attributes
            changed.append(field_id)
        records = {}
    else:
        ids = sorted(set(session.scalars(select(UserField.field_id))))
        for index, field_id in enumerate(ids):
            if field_id in records:
                continue
            field = session.get(FieldRecord, field_id, with_for_update=True)
            attributes = deepcopy(field.attributes)
            original_properties = deepcopy(attributes.get("properties"))
            properties = deepcopy(original_properties or {})
            soil = properties.setdefault("soil", {})
            crop, soil_type, ph, organic, capacity, drainage = SAMPLES[index % len(SAMPLES)]
            supplied = dict(
                soilType=soil_type,
                soilPh=ph,
                organicMatter=organic,
                waterCapacity=capacity,
                drainage=drainage,
            )
            for key, value in supplied.items():
                if soil.get(key) is None:
                    soil[key] = value
            properties = PropertyData.model_validate(properties).model_dump(mode="json")
            sample_crop = field.crop or crop
            if sample_crop == field.crop and properties == original_properties:
                continue
            records[field_id] = dict(
                originalCrop=field.crop,
                originalProperties=original_properties,
                hadProperties="properties" in attributes,
                sampleCrop=sample_crop,
                sampleProperties=properties,
            )
            field.crop = sample_crop
            attributes["properties"] = properties
            field.attributes = attributes
            changed.append(field_id)
    metadata = dict(
        purpose="Temporary synthetic crop/soil inputs, explicitly requested for UI prototyping",
        updatedAt=datetime.now(timezone.utc).isoformat(),
        status="restored" if restore else "seeded",
        fields=records,
    )
    if backup:
        backup.metadata_ = metadata
    else:
        session.add(MapDataset(id=SEED_ID, metadata_=metadata))
    return dict(action="restored" if restore else "seeded", changed=len(changed), fields=changed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore", action="store_true")
    arguments = parser.parse_args()
    engine = database_engine(Settings().database_url)
    try:
        with session_factory(engine).begin() as session:
            result = seed(session, restore=arguments.restore)
        print(json.dumps(result))
    finally:
        engine.dispose()
