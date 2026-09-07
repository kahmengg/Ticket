"""Persist notification retries and event revisions."""
from alembic import op
import sqlalchemy as sa
from datetime import timezone

revision = "20260907_0002"
down_revision = "20260615_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    # Existing alert records represent successful sends and must not be replayed.
    op.add_column("alerts", sa.Column("delivery_state", sa.String(20), nullable=False, server_default="sent"))
    op.add_column("alerts", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("alerts", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("alerts", sa.Column("lease_token", sa.String(36)))
    op.add_column("alerts", sa.Column("sale_date", sa.DateTime(timezone=True)))
    op.create_index("ix_alerts_delivery_state", "alerts", ["delivery_state"])
    # Anchor old reminder identities before a future scrape changes their sale dates.
    alerts = sa.table("alerts", sa.column("id", sa.Integer), sa.column("event_id", sa.Integer),
                      sa.column("alert_type", sa.String), sa.column("sale_date", sa.DateTime(timezone=True)))
    events = sa.table("events", sa.column("id", sa.Integer), sa.column("sale_date", sa.DateTime(timezone=True)))
    connection = op.get_bind()
    rows = connection.execute(sa.select(alerts.c.id, alerts.c.alert_type, events.c.sale_date).join(
        events, alerts.c.event_id == events.c.id,
    ).where(alerts.c.alert_type.like("sale_reminder_%"))).all()
    for alert_id, alert_type, sale_date in rows:
        if sale_date is not None and ":" not in alert_type:
            sale_date = sale_date.replace(tzinfo=timezone.utc) if sale_date.tzinfo is None else sale_date.astimezone(timezone.utc)
            connection.execute(alerts.update().where(alerts.c.id == alert_id).values(
                alert_type=f"{alert_type}:{sale_date.isoformat()}", sale_date=sale_date,
            ))


def downgrade():
    op.drop_index("ix_alerts_delivery_state", table_name="alerts")
    for name in ("sale_date", "lease_token", "next_attempt_at", "attempts", "delivery_state"):
        op.drop_column("alerts", name)
    op.drop_column("events", "revision")
