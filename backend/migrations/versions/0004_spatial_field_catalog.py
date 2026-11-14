"""Index field extents and store bounded, preaggregated map overviews."""

import sqlalchemy as sa
from alembic import op

revision = "0004_spatial_field_catalog"
down_revision = "0003_fields_and_user_fields"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("fields") as table:
        table.alter_column("crop", existing_type=sa.String(30), nullable=True)
        table.alter_column("geometry", existing_type=sa.JSON(), nullable=True)
        table.add_column(sa.Column("source_id", sa.String(32), nullable=True))
        table.add_column(
            sa.Column(
                "boundary_kind", sa.String(24), nullable=False, server_default="user_geometry"
            )
        )
        for name, length in (("state_fips", 2), ("county_fips", 3), ("county", 80)):
            table.add_column(sa.Column(name, sa.String(length), nullable=True))
        for name in ("min_lon", "min_lat", "max_lon", "max_lat", "centroid_lon", "centroid_lat"):
            table.add_column(sa.Column(name, sa.Float(), nullable=True))
        table.create_unique_constraint("uq_fields_source_id", ["source_id"])
    # Backfill any user-entered polygons without changing their supplied geometry.
    fields = sa.table(
        "fields",
        sa.column("id"),
        sa.column("geometry", sa.JSON()),
        *[
            sa.column(n, sa.Float())
            for n in ("min_lon", "min_lat", "max_lon", "max_lat", "centroid_lon", "centroid_lat")
        ],
    )
    connection = op.get_bind()

    def geometry_bounds(geometry):
        polygons = geometry["coordinates"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        points = [p for polygon in polygons for ring in polygon for p in ring]
        return (
            min(p[0] for p in points),
            min(p[1] for p in points),
            max(p[0] for p in points),
            max(p[1] for p in points),
        )

    for row in connection.execute(sa.select(fields.c.id, fields.c.geometry)).mappings():
        west, south, east, north = geometry_bounds(row["geometry"])
        connection.execute(
            fields.update()
            .where(fields.c.id == row["id"])
            .values(
                min_lon=west,
                min_lat=south,
                max_lon=east,
                max_lat=north,
                centroid_lon=(west + east) / 2,
                centroid_lat=(south + north) / 2,
            )
        )
    if connection.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_fields_spatial ON fields USING gist "
            "(box(point(min_lon, min_lat), point(max_lon, max_lat)))"
        )
    op.create_table(
        "field_map_cells",
        sa.Column("level", sa.Integer(), primary_key=True),
        sa.Column("x", sa.Integer(), primary_key=True),
        sa.Column("y", sa.Integer(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
        *[
            sa.Column(n, sa.Float(), nullable=False)
            for n in ("area", "min_lon", "min_lat", "max_lon", "max_lat")
        ],
    )
    op.create_table(
        "map_datasets",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    # Keep this historical polygon backfill independent of the current point model.
    for level in (4, 6, 8, 10, 12):
        connection.execute(
            sa.text("""
            INSERT INTO field_map_cells (level, x, y, count, area, min_lon, min_lat, max_lon, max_lat)
            SELECT :level, CAST(floor((centroid_lon + 180) / 360 * :size) AS INTEGER),
                   CAST(floor((centroid_lat + 90) / 180 * :size) AS INTEGER),
                   count(*), sum(area), min(min_lon), min(min_lat), max(max_lon), max(max_lat)
            FROM fields WHERE centroid_lon IS NOT NULL GROUP BY 2, 3
        """),
            dict(level=level, size=1 << level),
        )


def downgrade():
    op.drop_table("map_datasets")
    op.drop_table("field_map_cells")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.drop_index("ix_fields_spatial", table_name="fields")
    # Imported estimates cannot be represented by the old non-null polygon schema.
    op.execute("DELETE FROM fields WHERE source_id IS NOT NULL")
    with op.batch_alter_table("fields") as table:
        table.drop_constraint("uq_fields_source_id", type_="unique")
        for name in (
            "source_id",
            "boundary_kind",
            "state_fips",
            "county_fips",
            "county",
            "min_lon",
            "min_lat",
            "max_lon",
            "max_lat",
            "centroid_lon",
            "centroid_lat",
        ):
            table.drop_column(name)
        table.alter_column("crop", existing_type=sa.String(30), nullable=False)
        table.alter_column("geometry", existing_type=sa.JSON(), nullable=False)
