"""Store each account's own prices, production costs and land rent for a selected field."""

import sqlalchemy as sa
from alembic import op

revision = "0008_field_economics"
down_revision = "0007_farmer_inputs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_fields", sa.Column("economics", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("user_fields", "economics")
