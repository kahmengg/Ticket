"""Preview source extraction and merging using an isolated database, without Telegram."""
import argparse
import json
from pathlib import Path
import sys

# Support running this script directly from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.scrapers.livenation_sg import LiveNationSGScraper
from app.scrapers.ticketmaster_sg import TicketmasterSGScraper
from app.services.event_detector import process_events
from app.schemas import EventRead


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["both", "livenation", "ticketmaster"], default="both")
    parser.add_argument("--output", type=Path, default=Path(".scratch/preview.json"))
    parser.add_argument("--ticketmaster-cache", type=Path, help="Read previously saved public detail HTML instead of fetching Ticketmaster again.")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    observations, reports = [], []
    scrapers = []
    if args.source in {"both", "livenation"}:
        scrapers.append(LiveNationSGScraper())
    if args.source in {"both", "ticketmaster"}:
        scrapers.append(TicketmasterSGScraper())
    for scraper in scrapers:
        try:
            if isinstance(scraper, TicketmasterSGScraper) and args.ticketmaster_cache:
                events = [event for path in sorted(args.ticketmaster_cache.glob("*sg_*.html"))
                          for event in scraper.parse_detail(path.read_text(encoding="utf-8"), f"https://ticketmaster.sg/activity/detail/{path.stem}")]
            else:
                events = scraper.fetch_events()
            observations.extend(events)
            reports.append(dict(source=scraper.source_name, count=len(events), errors=getattr(scraper, "errors", []),
                                warnings=getattr(scraper, "warnings", [])))
        except Exception as exc:
            reports.append(dict(source=scraper.source_name, count=0, errors=[type(exc).__name__], warnings=[]))
    # This engine is independent of DATABASE_URL and never calls the notification pipeline.
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = process_events(db, observations)
        data = dict(sources=reports, performances=len(result.new_events),
                    merged=sum(len(event.listings) > 1 for event in result.new_events),
                    events=[EventRead.model_validate(event).model_dump(mode="json") for event in result.new_events])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in data.items() if key != "events"}, ensure_ascii=False, indent=2))
    print(f"Saved {args.output}")
    return 1 if any(report["errors"] for report in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
