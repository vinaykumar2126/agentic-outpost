import asyncio
import json
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Event, ScrapeRun

logger = logging.getLogger(__name__)


def upsert_events(db: Session, raw_events, scrape_run: ScrapeRun) -> None:
    from app.connectors.base import RawEvent

    for raw in raw_events:
        scrape_run.events_fetched += 1
        existing = (
            db.query(Event)
            .filter(Event.source == raw.source, Event.external_id == raw.external_id)
            .first()
        )

        short_desc = raw.description[:400] if raw.description else ""
        tags_json = json.dumps(raw.tags) if raw.tags else None
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if existing is None:
            db.add(
                Event(
                    external_id=raw.external_id,
                    source=raw.source,
                    title=raw.title,
                    description=raw.description,
                    short_description=short_desc,
                    url=raw.url,
                    start_datetime=raw.start_datetime,
                    end_datetime=raw.end_datetime,
                    location_name=raw.location_name,
                    location_address=raw.location_address,
                    is_online=raw.is_online,
                    organizer_name=raw.organizer_name,
                    tags=tags_json,
                    is_free=raw.is_free,
                    price_min=raw.price_min,
                    price_max=raw.price_max,
                    fetched_at=now,
                )
            )
            scrape_run.events_new += 1
        else:
            content_changed = (
                existing.title != raw.title or existing.description != raw.description
            )
            existing.title = raw.title
            existing.description = raw.description
            existing.short_description = short_desc
            existing.url = raw.url
            existing.start_datetime = raw.start_datetime
            existing.end_datetime = raw.end_datetime
            existing.location_name = raw.location_name
            existing.location_address = raw.location_address
            existing.is_online = raw.is_online
            existing.organizer_name = raw.organizer_name
            existing.tags = tags_json
            existing.is_free = raw.is_free
            existing.price_min = raw.price_min
            existing.price_max = raw.price_max
            existing.fetched_at = now
            if content_changed:
                # Title/description changed means the old score is stale — re-rank on next run
                existing.relevance_score = None
                existing.relevance_justification = None
                existing.ranked_at = None
            scrape_run.events_updated += 1

    db.commit()


def nightly_scrape_job(source_filter: str | None = None) -> None:
    # Deferred imports avoid circular import at module load time
    from app.connectors.registry import get_active_connectors
    from app.ranking.event_ranker import EventRanker

    db = SessionLocal()
    try:
        connectors = get_active_connectors()
        if source_filter:
            connectors = [c for c in connectors if c.source_name == source_filter]

        for connector in connectors:
            run = ScrapeRun(source=connector.source_name, status="running")
            db.add(run)
            db.commit()

            try:
                # Connectors are async (MCP uses async I/O); APScheduler calls jobs synchronously
                raw_events = asyncio.run(connector.fetch_events())
                upsert_events(db, raw_events, run)

                ranker = EventRanker()
                run.events_ranked = ranker.rank_unscored(db)

                run.status = "success"
            except Exception as exc:
                logger.error("Scrape failed for %s: %s", connector.source_name, exc)
                run.status = "failed"
                run.error_message = str(exc)
            finally:
                run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="America/Los_Angeles")
    scheduler.add_job(nightly_scrape_job, "cron", hour=2, minute=0, id="nightly_scrape")
    return scheduler
