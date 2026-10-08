"""Human-readable status shared by alerts and catalogue browsing."""
from datetime import datetime, timezone
from app.services.sale_windows import utc


def status_text(event, now=None):
    now = now or datetime.now(timezone.utc)
    if event.status == "unavailable":
        future_sale = event.sale_date and utc(event.sale_date) > now
        return "General sale not open yet" if future_sale else "Not currently on sale"
    return {"tickets_listed": "See ticket site for availability", "active": "Listed",
            "sold_out": "Sold out", "cancelled": "Cancelled", "postponed": "Postponed",
            "rescheduled": "Rescheduled"}.get(event.status, "Availability unconfirmed")
