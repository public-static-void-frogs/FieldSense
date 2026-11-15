"""Accept / decline decisions a user made on calendar events."""

from sqlalchemy import CheckConstraint, ForeignKey, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base


class EventResponseRecord(Base):
    __tablename__ = "event_responses"
    __table_args__ = (
        CheckConstraint("status IN ('accepted', 'declined')", name="valid_event_response"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    field_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fields.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10))
    # Identifies the reviewed schedule: a response to a changed event no longer applies.
    fingerprint: Mapped[str] = mapped_column(String(2000))


class EventResponses:
    def __init__(self, session: Session, user_id: str):
        self.session, self.user_id = session, user_id

    def all(self) -> dict[str, dict[str, str]]:
        rows = self.session.scalars(
            select(EventResponseRecord).where(EventResponseRecord.user_id == self.user_id)
        )
        return {
            row.event_id: {"status": row.status, "fingerprint": row.fingerprint} for row in rows
        }

    def _field_rows(self, field_id: str) -> dict[str, EventResponseRecord]:
        rows = self.session.scalars(
            select(EventResponseRecord).where(
                EventResponseRecord.user_id == self.user_id,
                EventResponseRecord.field_id == field_id,
            )
        )
        return {row.event_id: row for row in rows}

    def replace_for_field(
        self,
        field_id: str,
        status: str,
        fingerprints: dict[str, str],
        only_proposed: bool = False,
    ) -> dict[str, dict[str, str]]:
        """Set one decision for the given events of a field and drop its older responses.

        ``proposed`` clears the decisions. With ``only_proposed`` the events that already have a
        valid decision keep it and only the others get ``status``. Responses to events that no
        longer exist are removed so the table does not grow with every changed date.
        """
        rows = self._field_rows(field_id)
        keep = {
            event_id
            for event_id, row in rows.items()
            if only_proposed
            and status != "proposed"
            and fingerprints.get(event_id) == row.fingerprint
        }
        for event_id, row in rows.items():
            if event_id not in keep:
                self.session.delete(row)
        self.session.flush()
        if status != "proposed":
            self.session.add_all(
                EventResponseRecord(
                    user_id=self.user_id,
                    event_id=event_id,
                    field_id=field_id,
                    status=status,
                    fingerprint=fingerprint,
                )
                for event_id, fingerprint in fingerprints.items()
                if event_id not in keep
            )
        self.session.commit()
        return self.all()

    def set_one(
        self, field_id: str, event_id: str, status: str, fingerprints: dict[str, str]
    ) -> dict[str, dict[str, str]]:
        """Set the decision of one event; ``proposed`` clears it.

        ``fingerprints`` are the field's current events: responses to other events are removed.
        """
        for other_id, row in self._field_rows(field_id).items():
            if other_id not in fingerprints or other_id == event_id:
                self.session.delete(row)
        self.session.flush()
        if status != "proposed":
            self.session.add(
                EventResponseRecord(
                    user_id=self.user_id,
                    event_id=event_id,
                    field_id=field_id,
                    status=status,
                    fingerprint=fingerprints[event_id],
                )
            )
        self.session.commit()
        return self.all()
