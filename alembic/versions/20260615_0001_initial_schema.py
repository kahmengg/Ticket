"""initial schema

Revision ID: 20260615_0001
Revises: None
Create Date: 2026-06-15 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260615_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "artists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artists_id"), "artists", ["id"], unique=False)
    op.create_index(op.f("ix_artists_name"), "artists", ["name"], unique=True)

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_sources_id"), "sources", ["id"], unique=False)

    op.create_table(
        "telegram_subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=100), nullable=False),
        sa.Column("from_id", sa.String(length=100), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("chat_type", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_telegram_subscribers_chat_id"), "telegram_subscribers", ["chat_id"], unique=True)
    op.create_index(op.f("ix_telegram_subscribers_from_id"), "telegram_subscribers", ["from_id"], unique=False)
    op.create_index(op.f("ix_telegram_subscribers_id"), "telegram_subscribers", ["id"], unique=False)
    op.create_index(op.f("ix_telegram_subscribers_is_active"), "telegram_subscribers", ["is_active"], unique=False)
    op.create_index(op.f("ix_telegram_subscribers_username"), "telegram_subscribers", ["username"], unique=False)

    op.create_table(
        "venues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_venues_id"), "venues", ["id"], unique=False)
    op.create_index(op.f("ix_venues_name"), "venues", ["name"], unique=False)

    op.create_table(
        "watchlist_keywords",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=100), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("normalized_keyword", sa.String(length=255), nullable=False),
        sa.Column("compact_keyword", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "normalized_keyword", name="uq_watchlist_chat_keyword"),
    )
    op.create_index(op.f("ix_watchlist_keywords_chat_id"), "watchlist_keywords", ["chat_id"], unique=False)
    op.create_index(op.f("ix_watchlist_keywords_compact_keyword"), "watchlist_keywords", ["compact_keyword"], unique=False)
    op.create_index(op.f("ix_watchlist_keywords_id"), "watchlist_keywords", ["id"], unique=False)
    op.create_index(op.f("ix_watchlist_keywords_is_active"), "watchlist_keywords", ["is_active"], unique=False)
    op.create_index(op.f("ix_watchlist_keywords_normalized_keyword"), "watchlist_keywords", ["normalized_keyword"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("artist_name", sa.String(length=255), nullable=True),
        sa.Column("venue_name", sa.String(length=255), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("presale_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title", "venue_name", "event_date", name="uq_event_identity"),
    )
    op.create_index(op.f("ix_events_artist_name"), "events", ["artist_name"], unique=False)
    op.create_index(op.f("ix_events_content_hash"), "events", ["content_hash"], unique=False)
    op.create_index(op.f("ix_events_event_date"), "events", ["event_date"], unique=False)
    op.create_index(op.f("ix_events_id"), "events", ["id"], unique=False)
    op.create_index(op.f("ix_events_sale_date"), "events", ["sale_date"], unique=False)
    op.create_index(op.f("ix_events_source_id"), "events", ["source_id"], unique=False)
    op.create_index(op.f("ix_events_status"), "events", ["status"], unique=False)
    op.create_index(op.f("ix_events_title"), "events", ["title"], unique=False)
    op.create_index(op.f("ix_events_url"), "events", ["url"], unique=True)
    op.create_index(op.f("ix_events_venue_name"), "events", ["venue_name"], unique=False)

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("chat_id", sa.String(length=100), nullable=True),
        sa.Column("alert_type", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "alert_type", "chat_id", name="uq_alert_event_type_chat"),
    )
    op.create_index(op.f("ix_alerts_chat_id"), "alerts", ["chat_id"], unique=False)
    op.create_index(op.f("ix_alerts_event_id"), "alerts", ["event_id"], unique=False)
    op.create_index(op.f("ix_alerts_id"), "alerts", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alerts_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_event_id"), table_name="alerts")
    op.drop_index(op.f("ix_alerts_chat_id"), table_name="alerts")
    op.drop_table("alerts")

    op.drop_index(op.f("ix_events_venue_name"), table_name="events")
    op.drop_index(op.f("ix_events_url"), table_name="events")
    op.drop_index(op.f("ix_events_title"), table_name="events")
    op.drop_index(op.f("ix_events_status"), table_name="events")
    op.drop_index(op.f("ix_events_source_id"), table_name="events")
    op.drop_index(op.f("ix_events_sale_date"), table_name="events")
    op.drop_index(op.f("ix_events_id"), table_name="events")
    op.drop_index(op.f("ix_events_event_date"), table_name="events")
    op.drop_index(op.f("ix_events_content_hash"), table_name="events")
    op.drop_index(op.f("ix_events_artist_name"), table_name="events")
    op.drop_table("events")

    op.drop_index(op.f("ix_watchlist_keywords_normalized_keyword"), table_name="watchlist_keywords")
    op.drop_index(op.f("ix_watchlist_keywords_is_active"), table_name="watchlist_keywords")
    op.drop_index(op.f("ix_watchlist_keywords_id"), table_name="watchlist_keywords")
    op.drop_index(op.f("ix_watchlist_keywords_compact_keyword"), table_name="watchlist_keywords")
    op.drop_index(op.f("ix_watchlist_keywords_chat_id"), table_name="watchlist_keywords")
    op.drop_table("watchlist_keywords")

    op.drop_index(op.f("ix_venues_name"), table_name="venues")
    op.drop_index(op.f("ix_venues_id"), table_name="venues")
    op.drop_table("venues")

    op.drop_index(op.f("ix_telegram_subscribers_username"), table_name="telegram_subscribers")
    op.drop_index(op.f("ix_telegram_subscribers_is_active"), table_name="telegram_subscribers")
    op.drop_index(op.f("ix_telegram_subscribers_id"), table_name="telegram_subscribers")
    op.drop_index(op.f("ix_telegram_subscribers_from_id"), table_name="telegram_subscribers")
    op.drop_index(op.f("ix_telegram_subscribers_chat_id"), table_name="telegram_subscribers")
    op.drop_table("telegram_subscribers")

    op.drop_index(op.f("ix_sources_id"), table_name="sources")
    op.drop_table("sources")

    op.drop_index(op.f("ix_artists_name"), table_name="artists")
    op.drop_index(op.f("ix_artists_id"), table_name="artists")
    op.drop_table("artists")
