"""Keep mock and live assessment snapshots separate."""

import sqlalchemy as sa
from alembic import op

revision = "0010_assessment_mode"
down_revision = "0009_assessments"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "job_assessments",
        sa.Column("integration_mode", sa.String(10), server_default="mock", nullable=False),
    )
    op.alter_column("job_assessments", "integration_mode", server_default=None)
    op.drop_constraint("uq_assessment_versions", "job_assessments", type_="unique")
    op.create_unique_constraint(
        "uq_assessment_versions",
        "job_assessments",
        [
            "job_revision_id",
            "profile_revision_id",
            "config_id",
            "policy_version",
            "integration_mode",
        ],
    )


def downgrade():
    # Refuse downgrade when modes have distinct results for the same snapshot.
    op.drop_constraint("uq_assessment_versions", "job_assessments", type_="unique")
    op.create_unique_constraint(
        "uq_assessment_versions",
        "job_assessments",
        ["job_revision_id", "profile_revision_id", "config_id", "policy_version"],
    )
    op.drop_column("job_assessments", "integration_mode")
