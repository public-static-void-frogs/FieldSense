"""Store the shared field catalog and each user's selected fields without demo seeds."""

import sqlalchemy as sa
from alembic import op

revision = "0003_fields_and_user_fields"
down_revision = "0002_location_coordinates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("parcel_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("crop", sa.String(30), nullable=False),
        sa.Column("area", sa.Float(), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("area > 0", name="positive_field_area"),
    )
    op.create_table(
        "user_fields",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "field_id",
            sa.String(36),
            sa.ForeignKey("fields.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_fields_field_id", "user_fields", ["field_id"])


def downgrade():
    op.drop_table("user_fields")
    op.drop_table("fields")
