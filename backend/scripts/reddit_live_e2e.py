"""Live end-to-end test for the Reddit connector (public RSS — needs GROQ_API_KEY only).

Usage:  cd backend && python3 scripts/reddit_live_e2e.py [--dry-run]

--dry-run: fetch + extract only, print results, skip DB writes.
Without it: full pipeline — fetch, upsert, rank, and print what the email would contain.
Note: the full run takes a few minutes (7s politeness gap between ~20 RSS fetches).
"""
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from app.connectors.reddit import RedditConnector  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="no DB writes")
    args = parser.parse_args()

    connector = RedditConnector()
    if not connector.is_available():
        print("FAIL: reddit.com RSS endpoint unreachable (network down or Reddit blocking)")
        return 1

    events = asyncio.run(connector.fetch_events())
    print(f"\n=== RedditConnector returned {len(events)} events ===")
    for ev in events:
        print(f"  [{ev.start_datetime:%Y-%m-%d %H:%M}] {ev.title[:70]}")
        print(f"      url={ev.url}")
        print(f"      loc={ev.location_name}  org={ev.organizer_name}  tags={ev.tags}")

    if args.dry_run or not events:
        return 0

    from app.database import SessionLocal, create_tables
    from app.models import ScrapeRun
    from app.ranking.event_ranker import EventRanker
    from app.scheduler.jobs import upsert_events

    create_tables()
    db = SessionLocal()
    try:
        run = ScrapeRun(source="reddit", status="running")
        db.add(run)
        db.commit()
        upsert_events(db, events, run)
        ranked = EventRanker().rank_unscored(db)
        run.status = "success"
        run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
        print(f"\nUpserted: {run.events_new} new / {run.events_updated} updated; ranked {ranked}")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
