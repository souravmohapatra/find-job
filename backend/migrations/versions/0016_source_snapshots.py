"""Bounded conditional HTTP snapshots for source collection."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_source_snapshots"
down_revision = "0015_notification_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_snapshots",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("url_hash", sa.String(64), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id", "url_hash"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
    )
    op.create_index("ix_source_snapshots_fetched_at", "source_snapshots", ["fetched_at"])


def downgrade():
    op.drop_table("source_snapshots")
