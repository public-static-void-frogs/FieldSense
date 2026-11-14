"""Store a user's selected map coordinates alongside their location label."""

import sqlalchemy as sa
from alembic import op

revision = "0002_location_coordinates"
down_revision = "0001_users_and_settings"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_settings") as table:
        table.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        table.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        table.create_check_constraint("valid_latitude", "latitude BETWEEN -90 AND 90")
        table.create_check_constraint("valid_longitude", "longitude BETWEEN -180 AND 180")
        table.create_check_constraint(
            "paired_coordinates", "(latitude IS NULL) = (longitude IS NULL)"
        )


def downgrade():
    with op.batch_alter_table("user_settings") as table:
        table.drop_constraint("paired_coordinates", type_="check")
        table.drop_constraint("valid_longitude", type_="check")
        table.drop_constraint("valid_latitude", type_="check")
        table.drop_column("longitude")
        table.drop_column("latitude")
