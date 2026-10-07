"""Immutable assessment snapshots, purged with their source profile."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009_assessments"
down_revision = "0008_generic_frontier"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_revision_id", sa.Uuid(), nullable=False),
        sa.Column("profile_revision_id", sa.Uuid(), nullable=False),
        sa.Column("config_id", sa.Uuid(), nullable=False),
        sa.Column("policy_version", sa.String(30), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("report", postgresql.JSONB(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_revision_id"], ["job_revisions.id"]),
        sa.ForeignKeyConstraint(
            ["profile_revision_id"], ["profile_revisions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["config_id"], ["ai_task_revisions.id"]),
        sa.ForeignKeyConstraint(["operation_id"], ["operation_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
        sa.UniqueConstraint(
            "job_revision_id",
            "profile_revision_id",
            "config_id",
            "policy_version",
            name="uq_assessment_versions",
        ),
        sa.CheckConstraint(
            "category IN ('match','possible_match','not_match')", name="assessment_category"
        ),
    )
    op.create_index("ix_job_assessments_job_revision_id", "job_assessments", ["job_revision_id"])


def downgrade():
    op.drop_table("job_assessments")
