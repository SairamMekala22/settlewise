"""Initial normalized finance, durable run, evidence, review, and audit schema."""

from alembic import op
from sqlalchemy import Table

from recon.persistence.models import Base

revision = "20260825_0001"
down_revision = None
branch_labels = None
depends_on = None

_INITIAL_TABLE_NAMES = (
    "tenants",
    "import_sessions",
    "import_rows",
    "settlements",
    "settlement_ledger_lines",
    "bank_transactions",
    "reconciliation_runs",
    "reconciliation_outcomes",
    "review_decisions",
    "audit_events",
)


def _initial_tables() -> list[Table]:
    """Freeze revision 0001 so later model additions cannot leak into its DDL."""
    return [Base.metadata.tables[name] for name in _INITIAL_TABLE_NAMES]


def upgrade() -> None:
    """Create the reviewed V1 schema from the frozen initial metadata."""
    Base.metadata.create_all(bind=op.get_bind(), tables=_initial_tables(), checkfirst=False)


def downgrade() -> None:
    """Drop only V1-owned tables in dependency-safe order."""
    Base.metadata.drop_all(bind=op.get_bind(), tables=_initial_tables(), checkfirst=False)
