"""Immutable fetched-page snapshots for queued job extraction."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_page_extractions"
down_revision = "0011_job_feedback"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "page_extractions",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("config_id", sa.Uuid(), nullable=True),
        sa.Column("integration_mode", sa.String(10), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("inventory", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "offset"),
        sa.UniqueConstraint("operation_id"),
        sa.ForeignKeyConstraint(["run_id"], ["collection_runs.id"]),
        sa.ForeignKeyConstraint(["operation_id"], ["operation_intents.id"]),
        sa.ForeignKeyConstraint(["config_id"], ["ai_task_revisions.id"]),
    )


def downgrade():
    op.drop_table("page_extractions")
