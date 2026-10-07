"""notification eligibility and daily digest ledger"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013_notification_ledger"
down_revision = "0012_page_extractions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("local_time", sa.String(length=5), nullable=False),
        sa.Column("include_empty", sa.Boolean(), nullable=False),
        sa.Column("next_date", sa.Date(), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("id = 1", name="single_notification_owner"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "notification_digests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=100), nullable=False),
        sa.Column("local_time", sa.String(length=5), nullable=False),
        sa.Column("settings_revision", sa.Integer(), nullable=False),
        sa.Column("profile_revision_id", sa.Uuid(), nullable=True),
        sa.Column("integration_mode", sa.String(length=10), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending','sending','sent','failed','unknown','skipped')",
            name="digest_state",
        ),
        sa.ForeignKeyConstraint(
            ["profile_revision_id"], ["profile_revisions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_date"),
    )
    op.create_table(
        "notification_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("digest_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('new','baseline','reassessment')", name="notification_event_kind"
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["job_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["digest_id"], ["notification_digests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id"),
    )
    op.create_index(
        op.f("ix_notification_events_job_id"), "notification_events", ["job_id"], unique=False
    )
    op.create_index(
        "ix_notification_pending", "notification_events", ["digest_id", "created_at"], unique=False
    )
    op.create_table(
        "notification_digest_items",
        sa.Column("digest_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["digest_id"], ["notification_digests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["notification_events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("digest_id", "event_id"),
    )


def downgrade():
    op.drop_table("notification_digest_items")
    op.drop_index("ix_notification_pending", table_name="notification_events")
    op.drop_index(op.f("ix_notification_events_job_id"), table_name="notification_events")
    op.drop_table("notification_events")
    op.drop_table("notification_digests")
    op.drop_table("notification_settings")
