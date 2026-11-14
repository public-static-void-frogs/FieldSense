"""Store account-owned crop boundaries and drop stored field names."""

import sqlalchemy as sa
from alembic import op

revision = "0006_saved_crop_areas"
down_revision = "0005_point_field_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fields", sa.Column("owner_id", sa.String(36), nullable=True))
    op.add_column("fields", sa.Column("boundary", sa.JSON(), nullable=True))
    with op.batch_alter_table("fields") as table:
        table.create_foreign_key(
            "fk_field_owner", "users", ["owner_id"], ["id"], ondelete="CASCADE"
        )
        table.drop_column("name")
    op.create_index(
        "uq_field_owner_crop",
        "fields",
        ["owner_id", "crop"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
        sqlite_where=sa.text("owner_id IS NOT NULL"),
    )


def downgrade():
    raise RuntimeError("Removed field names cannot be restored.")
