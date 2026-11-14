"""Accept / decline decisions a user made on calendar events."""

from sqlalchemy import CheckConstraint, ForeignKey, String, delete, select
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

    def replace_for_field(
        self, field_id: str, status: str, fingerprints: dict[str, str]
    ) -> dict[str, dict[str, str]]:
        """Set one decision for the given events of a field and drop its older responses.

        ``proposed`` clears the decisions. Responses to events that no longer exist are removed
        so the table does not grow with every changed date.
        """
        self.session.execute(
            delete(EventResponseRecord).where(
                EventResponseRecord.user_id == self.user_id,
                EventResponseRecord.field_id == field_id,
            )
        )
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
            )
        self.session.commit()
        return self.all()
