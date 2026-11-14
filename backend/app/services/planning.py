"""Planning resources remain empty until real schedules and plans are supplied."""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.errors import ResourceNotFound


def context(user):
    return dict(today=datetime.now(ZoneInfo(user.settings.time_zone)).date().isoformat())


def field_events(store, field_id):
    store.require_field(field_id)
    return []


def rotation(store, field_id):
    store.require_field(field_id)
    raise ResourceNotFound("Rotation plan not available")


def strategy(store, field_id):
    store.require_field(field_id)
    raise ResourceNotFound("Strategy not available")


def system_events(store):
    return []
