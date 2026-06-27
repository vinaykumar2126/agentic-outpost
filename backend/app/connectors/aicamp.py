import asyncio
import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from typing import List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.connectors.base import EventConnector, RawEvent

logger = logging.getLogger(__name__)

AICAMP_BASE = "https://www.aicamp.ai"

# City-filtered listing pages — only Bay Area events
_BAY_AREA_LISTING_URLS = [
    "https://www.aicamp.ai/event/eventsquery?city=US-San+Francisco",
    "https://www.aicamp.ai/event/eventsquery?city=US-Silicon+Valley",
]


class AicampConnector(EventConnector):
    source_name = "aicamp"

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["npx", "@playwright/mcp", "--version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def fetch_events(self, days_ahead: int = 60) -> List[RawEvent]:
        server_params = StdioServerParameters(
            command="npx",
            args=["@playwright/mcp", "--headless"],
        )
        raw_events: List[RawEvent] = []

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info("MCP playwright session initialized for AiCamp")

                event_urls = await self._collect_event_urls(session)
                logger.info("Found %d upcoming Bay Area event URLs on AiCamp", len(event_urls))

                for url in event_urls:
                    try:
                        event = await self._scrape_event_detail(session, url)
                        if event:
                            raw_events.append(event)
                            logger.info("Scraped: %s", event.title[:60])
                    except Exception as exc:
                        logger.warning("Failed to scrape %s: %s", url, exc)

        logger.info("AicampConnector fetched %d events", len(raw_events))
        return raw_events

    async def _collect_event_urls(self, session: ClientSession) -> List[str]:
        urls: set[str] = set()

        for listing_url in _BAY_AREA_LISTING_URLS:
            await session.call_tool("browser_navigate", {"url": listing_url})
            await asyncio.sleep(3)  # Wait for JS to render

            snapshot = await session.call_tool("browser_snapshot", {})
            text = self._extract_text(snapshot)
            found = self._parse_event_urls(text)
            urls.update(found)
            logger.debug("Found %d upcoming URLs on %s", len(found), listing_url)

        return list(urls)

    async def _scrape_event_detail(self, session: ClientSession, url: str) -> RawEvent | None:
        await session.call_tool("browser_navigate", {"url": url})
        await asyncio.sleep(2)

        # aicamp.ai is not Next.js — no __NEXT_DATA__ — snapshot only
        snapshot = await session.call_tool("browser_snapshot", {})
        return self._parse_from_snapshot(url, self._extract_text(snapshot))

    # ── Parsers ──────────────────────────────────────────────────────────────

    def _parse_event_urls(self, text: str) -> List[str]:
        """Extract upcoming event URLs. The listing pages show all history since 2023,
        so we parse the date from the event ID (format: WYYYYMMDDHH) and skip past events."""
        seen: set[str] = set()
        urls = []
        # aicamp snapshot uses full absolute URLs: "/url: https://www.aicamp.ai/event/eventdetails/W..."
        for event_id in re.findall(
            r"/url:\s+https://www\.aicamp\.ai/event/eventdetails/(\S+)", text
        ):
            if event_id in seen:
                continue
            seen.add(event_id)
            if self._event_id_is_upcoming(event_id):
                urls.append(f"{AICAMP_BASE}/event/eventdetails/{event_id}")
        return urls

    def _parse_from_snapshot(self, url: str, text: str) -> RawEvent | None:
        # Title: aicamp uses h4 for event titles on detail pages
        title = None
        m = re.search(r'heading "(.+?)" \[level=4\]', text)
        if m:
            title = m.group(1).strip()
        if not title:
            # Fallback: h1/h2 or page title (strip "| AICamp" suffix)
            for level in (1, 2):
                m = re.search(rf'heading "(.+?)" \[level={level}\]', text)
                if m:
                    title = m.group(1).strip()
                    break
        if not title:
            m = re.search(r"Page Title:\s+(.+?)(?:\s*\|\s*AICamp.*)?$", text, re.MULTILINE | re.IGNORECASE)
            if m:
                title = m.group(1).strip()
        if not title:
            return None

        start_dt = self._parse_date_from_snapshot(text)
        if not start_dt:
            return None

        # Location from Google Calendar link: location=US-San+Francisco or venue address
        location = None
        loc_m = re.search(r"location=([^&\"]+)", text)
        if loc_m:
            raw_loc = loc_m.group(1).replace("+", " ").replace("%20", " ")
            # Strip "US-" prefix: "US-San Francisco" → "San Francisco"
            location = re.sub(r"^US-", "", raw_loc).strip()
        if not location:
            loc_m = re.search(r"(San Francisco[^\n,\"']{0,40}|Silicon Valley[^\n,\"']{0,30})", text, re.IGNORECASE)
            if loc_m:
                location = loc_m.group(1).strip()

        is_online = bool(re.search(r"\b(virtual|online|zoom|webinar)\b", text, re.IGNORECASE))

        # Organizer: from eventsquery?organizer= links present on every event page
        organizer = None
        org_m = re.search(r"eventsquery\?organizer=([^\"'\s&]+)", text)
        if org_m:
            organizer = org_m.group(1).replace("+", " ").replace("%20", " ")

        # Description: paragraph elements in the event body
        desc_lines = re.findall(r'paragraph \[ref=[^\]]+\]:\s*"?([^"\n]{20,})', text)
        description = " ".join(desc_lines[:6])

        external_id = url.rstrip("/").split("/")[-1]

        return RawEvent(
            external_id=external_id,
            source=self.source_name,
            title=title,
            description=description[:2000] or title,
            url=url,
            start_datetime=start_dt,
            location_name=location,
            organizer_name=organizer,
            is_online=is_online,
            is_free=True,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _event_id_is_upcoming(event_id: str) -> bool:
        """Event IDs encode the date as WYYYYMMDDHH — skip past events without fetching detail pages."""
        m = re.match(r"W(\d{4})(\d{2})(\d{2})\d*", event_id)
        if not m:
            return True  # unknown format, include
        try:
            event_date = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return event_date >= datetime.now() - timedelta(days=1)
        except ValueError:
            return True

    @staticmethod
    def _parse_date_from_snapshot(text: str) -> datetime | None:
        """Handle aicamp's date format: 'Jul 15 2026, 05:00 PM PDT'
        Also handles 'Weekday, Month Day' + 'H:MM AM/PM' as a fallback.
        """
        now = datetime.now(timezone.utc)
        year = now.year

        # Primary: "Jul 15 2026, 05:00 PM PDT" — aicamp includes the year explicitly
        m = re.search(r"(\w+ \d{1,2} \d{4}),\s+(\d{1,2}:\d{2} [AP]M)", text)
        if m:
            try:
                dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%b %d %Y %I:%M %p")
                return dt
            except ValueError:
                pass

        # Fallback: "Weekday, Month Day" + "H:MM AM/PM" (same pattern as Luma)
        date_m = re.search(r"\w+day,\s+(\w+ \d{1,2})", text)
        if date_m:
            after_date = text[date_m.start():]
            time_m = re.search(r"(\d{1,2}:\d{2} [AP]M)", after_date)
            if time_m:
                try:
                    dt = datetime.strptime(
                        f"{date_m.group(1)} {year} {time_m.group(1)}", "%B %d %Y %I:%M %p"
                    )
                    if dt < now.replace(tzinfo=None) - timedelta(days=14):
                        dt = dt.replace(year=year + 1)
                    return dt
                except ValueError:
                    pass

        return None

    @staticmethod
    def _extract_text(tool_result) -> str:
        if hasattr(tool_result, "content"):
            for block in tool_result.content:
                if hasattr(block, "text"):
                    return block.text
        return str(tool_result)
