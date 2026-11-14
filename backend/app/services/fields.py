"""Read supplied field data without inventing agronomic observations."""

from copy import deepcopy

from app.core.errors import ResourceNotFound


def properties(field):
    if field["properties"] is None:
        raise ResourceNotFound("Field properties not available")
    return deepcopy(field["properties"])


def history(store, field_id):
    store.require_field(field_id)
    return dict(events=[], seasons=[])


def recommendation(store, field_id):
    store.require_field(field_id)
    raise ResourceNotFound("Recommendation not available")
