"""Store accepted and declined calendar events per account."""

import sqlalchemy as sa
from alembic import op

revision = "0007_event_responses"
down_revision = "0006_saved_crop_areas"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "event_responses",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("field_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("fingerprint", sa.String(2000), nullable=False),
        sa.CheckConstraint("status IN ('accepted', 'declined')", name="valid_event_response"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_id"], ["fields.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "event_id"),
    )
    op.create_index("ix_event_responses_field_id", "event_responses", ["field_id"])


def downgrade():
    op.drop_index("ix_event_responses_field_id", table_name="event_responses")
    op.drop_table("event_responses")
