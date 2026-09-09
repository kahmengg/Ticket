import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app import crud
from app.database import SessionLocal
from app.scrapers.livenation_sg import LiveNationSGScraper
from app.scrapers.ticketmaster_sg import SourceFetchError, TicketmasterSGScraper
from app.models import Event, utc_now
from app.services.source_matching import CANONICAL_FIELDS
from app.services.event_detector import DetectionResult, generate_content_hash, process_events
from app.services.notifications import deliver_pending_alerts, queue_event_alerts, send_sale_reminder_alerts
from app.services.job_lock import CheckAlreadyRunning, source_check_lock
from app.services.watchlist import sale_reminder_matches

logger = logging.getLogger(__name__)


def enabled_scrapers():
    scrapers = []
    if settings.enable_livenation:
        scrapers.append(LiveNationSGScraper())
    if settings.enable_ticketmaster:
        scrapers.append(TicketmasterSGScraper())
    return scrapers


def run_livenation_check(db: Session | None = None) -> DetectionResult:
    # Keep the original Python entry point for callers that explicitly request Live Nation.
    return run_event_check(db, scrapers=[LiveNationSGScraper()])


def run_event_check(db: Session | None = None, *, scrapers=None) -> DetectionResult:
    owns_session = db is None
    session = db or SessionLocal()
    result = DetectionResult()
    try:
        with source_check_lock(session.get_bind()) as acquired:
            if not acquired:
                raise CheckAlreadyRunning("An event check is already running.")
            batches = []
            for scraper in enabled_scrapers() if scrapers is None else scrapers:
                try:
                    observations = scraper.fetch_events()
                    if not observations:
                        raise ValueError("Empty source result")
                    batches.append((scraper, observations, None))
                except Exception as exc:
                    # Only our controlled scraper errors are safe to expose; library errors can contain secrets.
                    reason = str(exc) if isinstance(exc, SourceFetchError) else type(exc).__name__
                    batches.append((scraper, [], reason))
                    logger.warning("Source fetch failed: %s (%s)", scraper.source_name, reason)
            before = {event.id: (generate_content_hash({field: getattr(event, field) for field in CANONICAL_FIELDS}), event.revision)
                      for event in session.scalars(select(Event))}
            touched, eligible = set(), set()
            for scraper, observations, error in batches:
                source = crud.get_or_create_source(session, scraper.source_name, scraper.base_url)
                source.last_check_at = utc_now()
                seeded = source.baseline_at is None and not settings.send_alerts_on_first_run
                warnings = list(getattr(scraper, "warnings", []))
                errors = list(getattr(scraper, "errors", []))
                if error is None:
                    try:
                        # A bad provider batch rolls back independently, preserving the other source.
                        with session.begin_nested():
                            detected = process_events(session, observations, commit=False)
                        ids = {event.id for event in detected.new_events + detected.updated_events + detected.unchanged_events}
                        touched.update(ids)
                        if not seeded:
                            eligible.update(event.id for event in detected.new_events + detected.updated_events)
                        if not errors:
                            source.last_success_at = utc_now()
                            if source.baseline_at is None:
                                source.baseline_at = source.last_success_at
                    except Exception as exc:
                        error = type(exc).__name__
                        logger.warning("Source processing failed: %s (%s)", scraper.source_name, error)
                source.last_status = "failed" if error else ("partial" if errors else "ok")
                source.last_error = error or ("; ".join(errors)[:2000] if errors else None)
                source.last_event_count = len(observations) if error is None else 0
                source.last_warnings = warnings
                result.source_results.append(dict(name=source.name, status=source.last_status,
                                                  events=source.last_event_count, seeded=seeded and error is None,
                                                  error=source.last_error, warnings=warnings))
                session.flush()
            # Collapse all provider changes into one canonical revision and one alert per performance.
            for event_id in sorted(touched):
                event = session.get(Event, event_id)
                current_hash = generate_content_hash({field: getattr(event, field) for field in CANONICAL_FIELDS})
                previous = before.get(event_id)
                if previous is None:
                    event.revision = 1
                    result.new_events.append(event)
                elif previous[0] != current_hash:
                    event.revision = previous[1] + 1
                    result.updated_events.append(event)
                else:
                    event.revision = previous[1]
                    result.unchanged_events.append(event)
                event.content_hash = current_hash
            queue_event_alerts([event for event in result.new_events if event.id in eligible], "new_event", session)
            queue_event_alerts([event for event in result.updated_events if event.id in eligible], "event_updated", session)
            session.commit()
        # Retries and reminders still run when a source is temporarily unavailable.
        result.notifications_sent = run_sale_reminder_check(session)
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def run_sale_reminder_check(db: Session | None = None) -> int:
    owns_session = db is None
    session = db or SessionLocal()
    try:
        sent_count = deliver_pending_alerts(session)
        for reminder_hours in settings.sale_reminder_hours:
            sent_count += send_sale_reminder_alerts(
                sale_reminder_matches(session, reminder_hours),
                reminder_hours,
                session,
            )
        return sent_count
    finally:
        if owns_session:
            session.close()


def _scheduled_job() -> None:
    try:
        run_event_check()
    except Exception:
        logger.exception("Scheduled event check failed.")


def _scheduled_reminder_job() -> None:
    try:
        run_sale_reminder_check()
    except Exception:
        logger.exception("Scheduled sale reminder check failed.")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _scheduled_job,
        "interval",
        hours=settings.scrape_interval_hours,
        id="event_source_check",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _scheduled_reminder_job,
        "interval",
        minutes=settings.reminder_interval_minutes,
        id="ticket_sale_reminder_check",
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
