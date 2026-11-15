"""Give existing user fields the state and county of the nearest catalog field.

New fields get them on creation (app.services.maps.locate_county); this fills the ones made
before. A field with no catalog field within about 15 km keeps no state.
"""

import math

import sqlalchemy as sa
from alembic import op

revision = "0009_locate_user_fields"
down_revision = "0008_field_economics"
branch_labels = None
depends_on = None

DEGREES = 0.15  # as app.services.maps.LOCATE_DEGREES


def upgrade():
    bind = op.get_bind()
    missing = bind.execute(
        sa.text("SELECT id, longitude, latitude FROM fields WHERE state_fips IS NULL")
    ).fetchall()
    nearest = sa.text(
        """SELECT state_fips, county_fips, county FROM fields
        WHERE state_fips IS NOT NULL
          AND longitude BETWEEN :lon - :d AND :lon + :d
          AND latitude BETWEEN :lat - :d AND :lat + :d
        ORDER BY :ew * (longitude - :lon) * (longitude - :lon)
                 + (latitude - :lat) * (latitude - :lat)
        LIMIT 1"""
    )
    for field_id, lon, lat in missing:
        ew = math.cos(math.radians(lat)) ** 2
        near = bind.execute(nearest, dict(lon=lon, lat=lat, d=DEGREES, ew=ew)).first()
        if near is not None:
            bind.execute(
                sa.text(
                    "UPDATE fields SET state_fips = :s, county_fips = :c, county = :n"
                    " WHERE id = :id"
                ),
                dict(s=near[0], c=near[1], n=near[2], id=field_id),
            )


def downgrade():
    pass  # the filled codes cannot be told from imported ones; they are harmless to keep
