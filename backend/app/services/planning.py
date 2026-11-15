"""Planning resources: calendar events, rotation plan, strategy and the user's event responses.

Events come from ``calendar_events.py`` and the plan and strategy from ``rotation_strategy.py``.
Responses (accepted / declined) are stored per account, keyed by the event id, together with a
fingerprint of the reviewed event: when an event changes, an old response no longer applies.
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.errors import ResourceNotFound


def context(user):
    return dict(today=datetime.now(ZoneInfo(user.settings.time_zone)).date().isoformat())


def field_events(store, field_id, calendar, preferences):
    return calendar.for_field(store.require_field(field_id), preferences)


def rotation(store, field_id, strategy, preferences):
    return strategy.plan(store.require_field(field_id), preferences)


def strategy(store, field_id, strategies, preferences):
    return strategies.strategy(store.require_field(field_id), preferences)


def system_events(store, calendar, preferences):
    return calendar.for_fields(store.fields(), preferences)


def fingerprint(event) -> str:
    """The same string the frontend builds with JSON.stringify, so both sides agree."""
    parts = [event[key] for key in ("id", "fieldId", "date", "title", "description", "duration")]
    return json.dumps([str(part) for part in parts], ensure_ascii=False, separators=(",", ":"))


def respond(store, responses, field_id, status, calendar, preferences, only_proposed=False):
    """Record one decision for every calendar event of the field.

    With ``only_proposed`` the events that were already accepted or declined keep their decision.
    """
    field = store.require_field(field_id)
    events = calendar.for_field(field, preferences)
    return responses.replace_for_field(
        str(field_id),
        status,
        {str(event["id"]): fingerprint(event) for event in events},
        only_proposed,
    )


def respond_to_event(store, responses, field_id, event_id, status, calendar, preferences):
    """Record one decision for a single calendar event of the field."""
    field = store.require_field(field_id)
    events = {str(e["id"]): fingerprint(e) for e in calendar.for_field(field, preferences)}
    if str(event_id) not in events:
        raise ResourceNotFound("Event not found")
    return responses.set_one(str(field_id), str(event_id), status, events)
