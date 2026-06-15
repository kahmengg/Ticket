import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


load_dotenv()


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _list_from_env(value: str | None) -> list[str]:
    if value is None:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ticket_assistant.db")
    telegram_bot_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = os.getenv("TELEGRAM_CHAT_ID")
    telegram_chat_ids: list[str] = field(default_factory=list)
    telegram_webhook_secret: str | None = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    scrape_interval_hours: int = max(1, int(os.getenv("SCRAPE_INTERVAL_HOURS", "6")))
    enable_scheduler: bool = _bool_from_env(os.getenv("ENABLE_SCHEDULER"), False)
    send_alerts_on_first_run: bool = _bool_from_env(os.getenv("SEND_ALERTS_ON_FIRST_RUN"), False)
    livenation_sg_events_url: str = os.getenv(
        "LIVENATION_SG_EVENTS_URL",
        "https://www.livenation.sg/event/allevents?CountryIds=199&Genres=alternative-and-indie%2Ccountry%2Chip-hop-and-rap%2Cpop%2Crnb-and-soul%2Crock",
    )

    def __post_init__(self) -> None:
        chat_ids = _list_from_env(os.getenv("TELEGRAM_CHAT_IDS"))
        if self.telegram_chat_id:
            chat_ids.append(self.telegram_chat_id)
        deduped = list(dict.fromkeys(chat_ids))
        object.__setattr__(self, "telegram_chat_ids", deduped)


settings = Settings()
