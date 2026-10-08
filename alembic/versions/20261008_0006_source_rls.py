"""Protect backend-only source metadata from Supabase's public API."""
from alembic import op

revision = "20261008_0006"
down_revision = "20260910_0005"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        # With no public policies, only the trusted owner/backend can access these tables.
        for table in ("source_listings", "sale_windows"):
            op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")


def downgrade():
    # A schema rollback must not reopen public access to production data.
    pass
