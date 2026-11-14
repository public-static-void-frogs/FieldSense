"""Replace the polygon catalog and selections with an empty point catalog.

This intentionally deletes old fields. Accounts, settings and selections are preserved.
Load the supplied county archive with scripts/import_field_points.py afterwards.
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_point_field_catalog"
down_revision = "0004_spatial_field_catalog"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    op.create_table(
        "pending_field_selections",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("field_id", sa.String(36), primary_key=True),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute(
        "INSERT INTO pending_field_selections SELECT user_id, field_id, selected_at FROM user_fields"
    )
    if connection.dialect.name == "postgresql":
        op.execute("TRUNCATE user_fields, fields, field_map_cells")
        op.drop_index("ix_fields_spatial", table_name="fields")
    else:
        for table in ("user_fields", "fields", "field_map_cells"):
            op.execute(f"DELETE FROM {table}")
    op.execute("DELETE FROM map_datasets WHERE id = 'csb-2025'")
    with op.batch_alter_table("fields") as table:
        for column in (
            "geometry",
            "boundary_kind",
            "min_lon",
            "min_lat",
            "max_lon",
            "max_lat",
            "centroid_lon",
            "centroid_lat",
        ):
            table.drop_column(column)
        table.add_column(sa.Column("longitude", sa.Float(), nullable=False))
        table.add_column(sa.Column("latitude", sa.Float(), nullable=False))
        table.add_column(
            sa.Column("location_kind", sa.String(24), nullable=False, server_default="user_point")
        )
        table.create_check_constraint(
            "valid_field_longitude", "longitude >= -180 AND longitude <= 180"
        )
        table.create_check_constraint("valid_field_latitude", "latitude >= -90 AND latitude <= 90")
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_fields_spatial ON fields USING gist (point(longitude, latitude))"
        )


def downgrade():
    raise RuntimeError("The replaced polygon catalog cannot be restored by a schema downgrade.")
