"""Independent retry batches for explicit resends and test messages."""

import sqlalchemy as sa
from alembic import op

revision = "0015_notification_actions"
down_revision = "0014_notification_delivery"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("notification_deliveries", "digest_id", nullable=True)
    op.add_column("notification_deliveries", sa.Column("group_id", sa.Uuid(), nullable=True))
    op.add_column(
        "notification_deliveries", sa.Column("batch_attempt", sa.Integer(), nullable=True)
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("manual", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("""UPDATE notification_deliveries AS delivery
                  SET group_id = delivery.digest_id, batch_attempt = delivery.attempt,
                      deadline_at = digest.cutoff + INTERVAL '30 minutes'
                  FROM notification_digests AS digest WHERE digest.id = delivery.digest_id""")
    for name in ("group_id", "batch_attempt", "deadline_at"):
        op.alter_column("notification_deliveries", name, nullable=False)
    op.alter_column("notification_deliveries", "manual", server_default=None)
    op.create_index("ix_notification_deliveries_group_id", "notification_deliveries", ["group_id"])
    op.create_unique_constraint(
        "uq_delivery_batch_attempt", "notification_deliveries", ["group_id", "batch_attempt"]
    )


def downgrade():
    # Old schema cannot represent standalone tests. Do not silently delete history.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM notification_deliveries WHERE digest_id IS NULL) THEN
            RAISE EXCEPTION 'Handle standalone notification tests before downgrade';
        END IF;
    END $$""")
    op.drop_constraint("uq_delivery_batch_attempt", "notification_deliveries", type_="unique")
    op.drop_index("ix_notification_deliveries_group_id", table_name="notification_deliveries")
    for name in ("deadline_at", "manual", "batch_attempt", "group_id"):
        op.drop_column("notification_deliveries", name)
    op.alter_column("notification_deliveries", "digest_id", nullable=False)
