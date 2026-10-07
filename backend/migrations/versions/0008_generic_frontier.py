"""Persist generic collection page frontiers."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_generic_frontier"
down_revision = "0007_search"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "collection_runs",
        sa.Column(
            "frontier", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )
    op.alter_column("collection_runs", "frontier", server_default=None)


def downgrade():
    op.drop_column("collection_runs", "frontier")
