"""Distinguish provider costs, rejection estimates and owner-verified billing."""

import sqlalchemy as sa
from alembic import op

revision = "0004_billing"
down_revision = "0003_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inference_calls", sa.Column("cost_source", sa.String(30), nullable=True))
    op.add_column(
        "inference_calls", sa.Column("accounted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute(
        "UPDATE inference_calls SET cost_source = 'legacy_reported', accounted_at = finished_at "
        "WHERE reported_usd IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("inference_calls", "accounted_at")
    op.drop_column("inference_calls", "cost_source")
