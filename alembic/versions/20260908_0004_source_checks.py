"""Track successful baselines and health independently for each source."""
from alembic import op
import sqlalchemy as sa

revision = "20260908_0004"
down_revision = "20260907_0003"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("baseline_at", "last_check_at", "last_success_at"):
        op.add_column("sources", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("sources", sa.Column("last_status", sa.String(20), nullable=False, server_default="never"))
    op.add_column("sources", sa.Column("last_error", sa.Text()))
    op.add_column("sources", sa.Column("last_event_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sources", sa.Column("last_warnings", sa.JSON(), nullable=False, server_default="[]"))
    # Existing imported sources already have a baseline; only newly enabled providers seed silently.
    op.execute(sa.text("UPDATE sources SET baseline_at = (SELECT MIN(first_seen_at) FROM source_listings WHERE source_listings.source_id = sources.id)"))


def downgrade():
    for name in ("last_warnings", "last_event_count", "last_error", "last_status", "last_success_at", "last_check_at", "baseline_at"):
        op.drop_column("sources", name)
