"""Persist accounts and one settings record per account."""

import sqlalchemy as sa
from alembic import op

revision = "0001_users_and_settings"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("auth_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_settings",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("farm_name", sa.String(120), nullable=False),
        sa.Column("location", sa.String(200), nullable=False),
        sa.Column("season", sa.String(4), nullable=False),
        sa.Column("time_zone", sa.String(100), nullable=False),
        sa.Column("units", sa.String(10), nullable=False),
        sa.Column("theme", sa.String(10), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("session_lifetime_hours", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "session_lifetime_hours BETWEEN 1 AND 720", name="valid_session_lifetime"
        ),
    )


def downgrade():
    op.drop_table("user_settings")
    op.drop_table("users")
