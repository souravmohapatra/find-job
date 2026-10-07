"""notification delivery attempts"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014_notification_delivery"
down_revision = "0013_notification_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("digest_id", sa.Uuid(), nullable=False),
        sa.Column("operation_id", sa.Uuid(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("target", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("remote_id", sa.String(length=100), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('pending','sending','sent','failed','unknown')", name="delivery_state"
        ),
        sa.ForeignKeyConstraint(["digest_id"], ["notification_digests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["operation_intents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_id"),
    )
    op.create_index(
        "ix_delivery_due", "notification_deliveries", ["state", "available_at"], unique=False
    )
    op.create_index(
        op.f("ix_notification_deliveries_digest_id"),
        "notification_deliveries",
        ["digest_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f("ix_notification_deliveries_digest_id"), table_name="notification_deliveries"
    )
    op.drop_index("ix_delivery_due", table_name="notification_deliveries")
    op.drop_table("notification_deliveries")
