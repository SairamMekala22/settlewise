"""Initial normalized finance, durable run, evidence, review, and audit schema."""

from alembic import op

from recon.persistence.models import Base

revision = "20260825_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the reviewed V1 schema from the frozen initial metadata."""
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)


def downgrade() -> None:
    """Drop only V1-owned tables in dependency-safe order."""
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
