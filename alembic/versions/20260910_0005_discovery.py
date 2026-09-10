"""Separate real discoveries from historical catalogue imports."""
from alembic import op
import sqlalchemy as sa
import re
import unicodedata

revision = "20260910_0005"
down_revision = "20260908_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("discovery_kind", sa.String(20), nullable=False, server_default="legacy"))
    op.add_column("events", sa.Column("discovered_at", sa.DateTime(timezone=True)))
    op.add_column("events", sa.Column("sort_title", sa.String(500), nullable=False, server_default=""))
    # Historical import timestamps do not establish publication/discovery order.
    connection = op.get_bind()
    for row in connection.execute(sa.text("SELECT id, title FROM events")).mappings().all():
        title = " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", row["title"]).casefold()))
        connection.execute(sa.text("UPDATE events SET sort_title=:title WHERE id=:id"), dict(title=title, id=row["id"]))
    op.create_index("ix_events_discovery_kind", "events", ["discovery_kind"])
    op.create_index("ix_events_discovered_at", "events", ["discovered_at"])
    op.create_index("ix_events_browse_discovery", "events", ["discovery_kind", "discovered_at", "sort_title", "event_date", "id"])
    op.create_index("ix_events_browse_upcoming", "events", ["event_date", "sort_title", "id"])


def downgrade():
    for name in ("ix_events_browse_upcoming", "ix_events_browse_discovery", "ix_events_discovered_at", "ix_events_discovery_kind"):
        op.drop_index(name, table_name="events")
    for name in ("sort_title", "discovered_at", "discovery_kind"):
        op.drop_column("events", name)
