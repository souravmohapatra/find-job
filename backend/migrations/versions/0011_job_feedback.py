"""Owner feedback, independent of matching decisions."""

import sqlalchemy as sa
from alembic import op

revision = "0011_job_feedback"
down_revision = "0010_assessment_mode"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "job_feedback",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.String(20), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.CheckConstraint("value IN ('relevant','not_relevant')", name="feedback_value"),
    )


def downgrade():
    op.drop_table("job_feedback")
