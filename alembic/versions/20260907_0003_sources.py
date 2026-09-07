"""Retain independent source listings and sale windows for each performance."""
from datetime import timezone
from urllib.parse import urlsplit

from alembic import op
import sqlalchemy as sa

revision = "20260907_0003"
down_revision = "20260907_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("ix_events_url", table_name="events")
    with op.batch_alter_table("events") as batch:
        batch.drop_constraint("uq_event_identity", type_="unique")
        batch.add_column(sa.Column("price_summary", sa.Text()))
        batch.add_column(sa.Column("currency", sa.String(3)))
        batch.add_column(sa.Column("field_provenance", sa.JSON(), nullable=False, server_default="{}"))
    op.create_index("ix_events_url", "events", ["url"])
    op.create_table(
        "source_listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(1000), nullable=False),
        sa.Column("url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("artist_name", sa.String(255)),
        sa.Column("venue_name", sa.String(255)),
        sa.Column("event_date", sa.DateTime(timezone=True)),
        sa.Column("sale_date", sa.DateTime(timezone=True)),
        sa.Column("presale_date", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(50)),
        sa.Column("price_summary", sa.Text()),
        sa.Column("currency", sa.String(3)),
        sa.Column("observed_data", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_listing_identity"),
    )
    for column in ("event_id", "source_id", "url"):
        op.create_index(f"ix_source_listings_{column}", "source_listings", [column])
    op.create_table(
        "sale_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), sa.ForeignKey("source_listings.id"), nullable=False),
        sa.Column("external_id", sa.String(500), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("listing_id", "external_id", name="uq_listing_sale_window"),
    )
    op.create_index("ix_sale_windows_listing_id", "sale_windows", ["listing_id"])
    _backfill()


def _backfill():
    connection = op.get_bind()
    metadata = sa.MetaData()
    events = sa.Table("events", metadata, autoload_with=connection)
    sources = sa.Table("sources", metadata, autoload_with=connection)
    listings = sa.Table("source_listings", metadata, autoload_with=connection)
    windows = sa.Table("sale_windows", metadata, autoload_with=connection)
    fields = ("title", "artist_name", "venue_name", "event_date", "sale_date", "presale_date", "url", "status")
    for event in connection.execute(sa.select(events)).mappings().all():
        source_id = event["source_id"]
        if source_id is None:
            # Keep older source-less events instead of omitting them from the new model.
            parsed = urlsplit(event["url"])
            name = f"Legacy: {parsed.netloc}"
            source_id = connection.scalar(sa.select(sources.c.id).where(sources.c.name == name))
            if source_id is None:
                source_id = connection.execute(sources.insert().values(
                    name=name, base_url=f"{parsed.scheme}://{parsed.netloc}",
                    source_type="legacy", created_at=event["created_at"],
                )).inserted_primary_key[0]
        values = {field: event[field] for field in fields}
        observed = {field: _json_value(value) for field, value in values.items()}
        listing_id = connection.execute(listings.insert().values(
            event_id=event["id"], source_id=source_id, external_id=event["url"],
            **values, observed_data=observed, first_seen_at=event["first_seen_at"],
            last_seen_at=event["last_seen_at"],
        )).inserted_primary_key[0]
        connection.execute(events.update().where(events.c.id == event["id"]).values(
            source_id=source_id,
            field_provenance={field: listing_id for field, value in values.items() if value is not None},
        ))
        for field, kind, name in (("sale_date", "general", "General sale"), ("presale_date", "presale", "Presale")):
            if event[field] is not None:
                connection.execute(windows.insert().values(
                    listing_id=listing_id, external_id=kind, name=name, kind=kind, starts_at=event[field],
                ))


def _json_value(value):
    if hasattr(value, "isoformat"):
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value.isoformat()
    return value


def downgrade():
    # Restoring URL uniqueness after multi-performance imports can destroy valid data.
    raise RuntimeError("Restore a backup to revert the source-listing migration safely.")
