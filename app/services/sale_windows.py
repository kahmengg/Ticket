"""Choose a single provider's sale windows and retain stable reminder identities."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReminderSale:
    kind: str
    name: str
    starts_at: datetime
    identity: str

    def key(self, hours):
        # Preserve existing general-sale keys so rollout cannot resend old reminders.
        if self.kind == "general":
            return f"sale_reminder_{hours}h:{utc(self.starts_at).isoformat()}"
        digest = hashlib.sha256(self.identity.encode()).hexdigest()[:20]
        return f"presale_reminder_{hours}h:{digest}:{utc(self.starts_at).isoformat()}"


def reminder_sales(event):
    result = []
    if event.sale_date:
        result.append(ReminderSale("general", "General sale", utc(event.sale_date), "general"))
    # Select the canonical presale provider, avoiding duplicate provider windows.
    provider = (event.field_provenance or {}).get("presale_date")
    listing = next((item for item in event.listings if item.id == provider), None)
    windows = [w for w in listing.sale_windows if w.kind == "presale" and w.starts_at] if listing else []
    seen = set()
    for window in windows:
        identity = " ".join(window.name.casefold().split())
        key = (identity, utc(window.starts_at))
        if key not in seen:
            result.append(ReminderSale("presale", window.name, utc(window.starts_at), identity))
            seen.add(key)
    if not windows and event.presale_date:
        result.append(ReminderSale("presale", "Presale", utc(event.presale_date), "presale"))
    return result
