import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import crud
from app.config import settings
from app.database import get_db
from app.schemas import EventRead, HealthRead, RunCheckRead, RunRemindersRead, SourceStatusRead, TelegramTestRead
from app.scheduler import run_event_check, run_sale_reminder_check
from app.models import Source
from app.services.notifications import get_notification_chat_ids, send_telegram_message, send_telegram_message_to_chat
from app.services.telegram_commands import handle_telegram_command
from app.services.job_lock import CheckAlreadyRunning

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
def run_check(
    response: Response,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> RunCheckRead:
    _require_run_check_authorization(authorization, settings.run_check_secret)
    try:
        result = run_event_check(db)
    except CheckAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not result.source_results:
        response.status_code = 503
    elif all(source["status"] == "failed" for source in result.source_results):
        response.status_code = 502
    return RunCheckRead(
        new_events=len(result.new_events),
        updated_events=len(result.updated_events),
        unchanged_events=len(result.unchanged_events),
        notifications_sent=result.notifications_sent,
        sources=result.source_results,
    )


@router.post("/run-reminders", response_model=RunRemindersRead)
def run_reminders(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> RunRemindersRead:
    # External wake-ups check only stored events; they never scrape more frequently.
    _require_run_check_authorization(authorization, settings.run_check_secret)
    return RunRemindersRead(notifications_sent=run_sale_reminder_check(db))


@router.get("/sources/status", response_model=list[SourceStatusRead])
def source_status(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> list:
    _require_run_check_authorization(authorization, settings.run_check_secret)
    return list(db.scalars(select(Source).order_by(Source.name)))


def _require_run_check_authorization(authorization: str | None, configured_secret: str | None) -> None:
    if not configured_secret:
        raise HTTPException(status_code=503, detail="Scheduled ticket checks are not configured.")

    scheme, separator, provided_secret = (authorization or "").partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not hmac.compare_digest(
        provided_secret.encode("utf-8"), configured_secret.encode("utf-8")
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid run-check credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/telegram/test-message", response_model=TelegramTestRead)
def telegram_test_message(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> TelegramTestRead:
    # Authenticate before looking up recipients or sending a broadcast.
    _require_run_check_authorization(authorization, settings.run_check_secret)
    chat_ids = get_notification_chat_ids(db)
    sent = send_telegram_message(
        "Ticket Sale Assistant test message. If you can see this, Telegram alerts are configured correctly.",
        chat_ids=chat_ids,
    )
    return TelegramTestRead(configured_chat_count=len(chat_ids), sent=sent)


@router.post("/telegram/webhook")
def telegram_webhook(
    update: dict,
    db: Session = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    # Missing configuration must never turn the public webhook into an open endpoint.
    if not settings.telegram_webhook_secret:
        raise HTTPException(status_code=503, detail="Telegram webhook is not configured.")
    if not hmac.compare_digest(
        (x_telegram_bot_api_secret_token or "").encode("utf-8"),
        settings.telegram_webhook_secret.encode("utf-8"),
    ):
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

    text = str(message.get("text") or "").strip()
    command_reply = handle_telegram_command(text, subscriber.chat_id, db)
    if command_reply:
        send_telegram_message_to_chat(subscriber.chat_id, command_reply)

    return {"ok": True, "saved": True, "chat_id": subscriber.chat_id}
