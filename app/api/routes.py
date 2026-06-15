from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.schemas import EventRead, HealthRead, RunCheckRead, TelegramTestRead
from app.scheduler import run_livenation_check
from app.services.notifications import get_notification_chat_ids, send_telegram_message, send_telegram_message_to_chat

router = APIRouter()


@router.get("/health", response_model=HealthRead)
def health() -> HealthRead:
    return HealthRead(status="ok")


@router.get("/events", response_model=list[EventRead])
def get_events(db: Session = Depends(get_db)) -> list:
    return crud.list_events(db)


@router.get("/events/upcoming", response_model=list[EventRead])
def get_upcoming_events(db: Session = Depends(get_db)) -> list:
    return crud.list_upcoming_events(db, datetime.now(timezone.utc))


@router.post("/run-check", response_model=RunCheckRead)
def run_check(db: Session = Depends(get_db)) -> RunCheckRead:
    try:
        result = run_livenation_check(db)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Live Nation SG fetch failed: {exc}",
        ) from exc
    return RunCheckRead(
        new_events=len(result.new_events),
        updated_events=len(result.updated_events),
        unchanged_events=len(result.unchanged_events),
        notifications_sent=result.notifications_sent,
    )


@router.post("/telegram/test-message", response_model=TelegramTestRead)
def telegram_test_message(db: Session = Depends(get_db)) -> TelegramTestRead:
    chat_ids = get_notification_chat_ids(db)
    sent = send_telegram_message(
        "Ticket Sale Assistant test message. If you can see this, Telegram alerts are configured correctly.",
        chat_ids=chat_ids,
    )
    return TelegramTestRead(configured_chat_ids=chat_ids, sent=sent)


@router.post("/telegram/webhook")
def telegram_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid Telegram webhook secret.")

    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return {"ok": True, "saved": False}

    chat = message.get("chat")
    sender = message.get("from")
    if not isinstance(chat, dict):
        return {"ok": True, "saved": False}

    chat_id = str(chat.get("id"))
    if not chat_id or chat_id == "None":
        return {"ok": True, "saved": False}

    sender = sender if isinstance(sender, dict) else {}
    subscriber = crud.upsert_telegram_subscriber(
        db,
        chat_id=chat_id,
        from_id=str(sender.get("id")) if sender.get("id") is not None else None,
        username=sender.get("username"),
        first_name=sender.get("first_name"),
        last_name=sender.get("last_name"),
        chat_type=chat.get("type"),
    )
    db.commit()

    text = str(message.get("text") or "").strip().lower()
    if text.startswith("/start"):
        send_telegram_message_to_chat(
            subscriber.chat_id,
            "You're subscribed to Ticket Sale Assistant alerts. I'll message this chat when new concerts are detected.",
        )

    return {"ok": True, "saved": True, "chat_id": subscriber.chat_id}
