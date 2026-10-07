"""Persist search budget reservations, cached results and provider cooldown."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_search"
down_revision = "0006_discovery"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "search_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("query", sa.String(1000), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["discovery_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "slot", name="uq_search_run_slot"),
        sa.CheckConstraint("slot BETWEEN 0 AND 2", name="search_slot"),
    )
    op.create_index("ix_search_requested_at", "search_requests", ["requested_at"])
    op.create_table(
        "search_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("search_state")
    op.drop_table("search_requests")
