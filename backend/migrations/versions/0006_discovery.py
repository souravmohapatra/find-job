"""Persist bounded discovery frontiers across worker restarts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_discovery"
down_revision = "6c37713d28ee"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("company_revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("frontier", postgresql.JSONB(), nullable=False),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("issues", postgresql.JSONB(), nullable=False),
        sa.Column("candidates", postgresql.JSONB(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('running','complete','partial','cancelled','expired')",
            name="discovery_state",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_company_state", "discovery_runs", ["company_id", "state"])


def downgrade():
    op.drop_table("discovery_runs")
