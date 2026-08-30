"""Add append-only AI investigation provenance.

Revision ID: 20260826_0002
Revises: 20260825_0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260826_0002"
down_revision = "20260825_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_investigations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("external_investigation_id", sa.String(length=72), nullable=False),
        sa.Column("settlement_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_template_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("response_hash", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("attempted_provider", sa.String(length=64), nullable=True),
        sa.Column("attempted_model", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["reconciliation_runs.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "external_investigation_id"),
    )
    op.create_index(
        "ix_ai_investigation_tenant_settlement_time",
        "ai_investigations",
        ["tenant_id", "settlement_id", "created_at"],
        unique=False,
    )
    for column in ("external_investigation_id", "run_id", "settlement_id", "tenant_id"):
        op.create_index(f"ix_ai_investigations_{column}", "ai_investigations", [column])


def downgrade() -> None:
    op.drop_table("ai_investigations")
