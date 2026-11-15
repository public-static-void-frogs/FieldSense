"""Store each account's own soil test and past season results for a selected field."""

import sqlalchemy as sa
from alembic import op

revision = "0007_farmer_inputs"
down_revision = "0006_saved_crop_areas"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_fields", sa.Column("soil_survey", sa.JSON(), nullable=True))
    op.add_column("user_fields", sa.Column("season_results", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("user_fields", "season_results")
    op.drop_column("user_fields", "soil_survey")
