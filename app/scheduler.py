import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app import crud
from app.database import SessionLocal
from app.scrapers.livenation_sg import LiveNationSGScraper
from app.services.event_detector import DetectionResult, process_events
from app.services.notifications import send_new_event_alerts, send_updated_event_alerts

logger = logging.getLogger(__name__)


def run_livenation_check(db: Session | None = None) -> DetectionResult:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        scraper = LiveNationSGScraper()
        scraped_events = scraper.fetch_events()
        is_first_run = crud.count_events(session) == 0
        result = process_events(session, scraped_events)
        if is_first_run and not settings.send_alerts_on_first_run:
            logger.info("Seeded initial event baseline without sending alerts.")
            return result
        result.notifications_sent = send_new_event_alerts(result.new_events, session)
        result.notifications_sent += send_updated_event_alerts(result.updated_events, session)
        return result
    finally:
        if owns_session:
            session.close()


def _scheduled_job() -> None:
    try:
        run_livenation_check()
    except Exception:
        logger.exception("Scheduled event check failed.")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_job,
        "interval",
        hours=settings.scrape_interval_hours,
        id="livenation_sg_event_check",
        replace_existing=True,
        max_instances=1,
    )
    return scheduler


def start_scheduler_if_enabled() -> BackgroundScheduler | None:
    if not settings.enable_scheduler:
        return None
    scheduler = create_scheduler()
    scheduler.start()
    return scheduler
