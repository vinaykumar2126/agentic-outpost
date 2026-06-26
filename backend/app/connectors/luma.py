import asyncio
import json
import logging
import re
import subprocess
from datetime import datetime, timedelta, timezone
from typing import List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.connectors.base import EventConnector, RawEvent

logger = logging.getLogger(__name__)

LUMA_BASE = "https://lu.ma"
LUMA_DISCOVER_URL = "https://lu.ma/sf"

_NON_EVENT_SLUGS = {
    "sf", "discover", "home", "login", "signup", "signin", "settings",
    "people", "user", "pricing", "app", "ai", "help", "calendar",
}


class LumaConnector(EventConnector):
    source_name = "luma"

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
                logger.info("MCP playwright session initialized")

                event_urls = await self._collect_event_urls(session)
                logger.info("Found %d candidate event URLs on Luma SF", len(event_urls))

                for url in event_urls:
                    try:
                        event = await self._scrape_event_detail(session, url)
                        if event:
                            raw_events.append(event)
                            logger.info("Scraped: %s", event.title[:60])
                    except Exception as exc:
                        logger.warning("Failed to scrape %s: %s", url, exc)

        logger.info("LumaConnector fetched %d events", len(raw_events))
        return raw_events

    async def _collect_event_urls(self, session: ClientSession) -> List[str]:
        await session.call_tool("browser_navigate", {"url": LUMA_DISCOVER_URL})
        await asyncio.sleep(3)

        urls: set[str] = set()
        for _ in range(4):
            snapshot = await session.call_tool("browser_snapshot", {})
            text = self._extract_text(snapshot)
            urls.update(self._parse_event_urls(text))
            await session.call_tool("browser_evaluate", {"function": "() => window.scrollBy(0, 900)"})
            await asyncio.sleep(2)

        return list(urls)

    async def _scrape_event_detail(self, session: ClientSession, url: str) -> RawEvent | None:
        await session.call_tool("browser_navigate", {"url": url})
        await asyncio.sleep(2)

        # Try structured data via JS first
        try:
            result = await session.call_tool("browser_evaluate", {
                "function": "() => JSON.stringify(window.__NEXT_DATA__?.props?.pageProps?.initialData ?? null)"
            })
            raw = self._extract_text(result)
            if raw and raw.strip() not in ("null", "undefined", "{}"):
                event = self._parse_from_next_data(url, raw)
                if event:
                    return event
        except Exception:
            pass

        snapshot = await session.call_tool("browser_snapshot", {})
        return self._parse_from_snapshot(url, self._extract_text(snapshot))

    # ── Parsers ──────────────────────────────────────────────────────────────

    def _parse_event_urls(self, text: str) -> List[str]:
        urls = []
        # Snapshot YAML uses "- /url: /slug" for relative links
        for slug in re.findall(r"/url:\s+/([a-zA-Z0-9][a-zA-Z0-9\-]{2,})", text):
            if slug not in _NON_EVENT_SLUGS:
                urls.append(f"{LUMA_BASE}/{slug}")
        return urls

    def _parse_from_next_data(self, url: str, json_text: str) -> RawEvent | None:
        try:
            data = json.loads(json_text)
            event_data = data.get("event") or data
            if not event_data.get("name"):
                return None

            title = event_data["name"]
            description = re.sub(r"<[^>]+>", " ", event_data.get("description", "")).strip()
            start_dt = self._parse_dt(event_data.get("start_at") or event_data.get("startTime"))
            if not start_dt:
                return None

            location = event_data.get("geo_address_info") or {}
            hosts = event_data.get("hosts") or [{}]
            organizer = hosts[0].get("name") if isinstance(hosts[0], dict) else None
            ticket_info = event_data.get("ticket_info") or {}
            tags = [t.get("label", "") for t in (event_data.get("tags") or [])]

            return RawEvent(
                external_id=url.rstrip("/").split("/")[-1],
                source=self.source_name,
                title=title,
                description=description[:2000],
                url=url,
                start_datetime=start_dt,
                end_datetime=self._parse_dt(event_data.get("end_at")),
                location_name=location.get("address") or location.get("city"),
                location_address=location.get("full_address"),
                is_online=bool(event_data.get("virtual") or event_data.get("is_virtual")),
                organizer_name=organizer,
                tags=tags,
                is_free=ticket_info.get("is_free", True),
                price_min=float(ticket_info["price"]) if ticket_info.get("price") else None,
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.debug("__NEXT_DATA__ parse failed for %s: %s", url, exc)
            return None

    def _parse_from_snapshot(self, url: str, text: str) -> RawEvent | None:
        # Title from page title line or h1
        title = None
        m = re.search(r"Page Title: (.+?) · Luma", text)
        if m:
            title = m.group(1).strip()
        if not title:
            m = re.search(r'heading "(.+?)" \[level=1\]', text)
            if m:
                title = m.group(1).strip()
        if not title:
            return None

        # Date: "Thursday, June 25" and "5:00 PM"
        start_dt = self._parse_date_from_snapshot(text)
        if not start_dt:
            return None

        # Location: look for city/address near location section
        location = None
        loc_m = re.search(r"(San Francisco[^\"'\n]*|[^\n]*San Francisco, CA)", text)
        if loc_m:
            location = loc_m.group(1).strip().strip('"')

        # Organizer: first link after "Hosted By"
        organizer = None
        org_m = re.search(r"Hosted By.*?link \"([^\"]+)\"", text, re.DOTALL)
        if org_m:
            organizer = org_m.group(1)

        # Description: paragraphs under "About Event"
        about_section = re.search(r"About Event\s*\n(.*?)(?:\n.*?Location|\Z)", text, re.DOTALL)
        desc_text = about_section.group(1) if about_section else text
        desc_lines = re.findall(r'paragraph \[ref=[^\]]+\]:\s*"?([^"\n]{15,})', desc_text)
        description = " ".join(desc_lines[:6])

        # Tags: short word slugs from /url: /tag-name links
        tags = []
        for slug in re.findall(r'/url:\s+/([a-z][a-z\-]{1,20})\b', text):
            if slug not in _NON_EVENT_SLUGS and slug not in tags:
                tags.append(slug)
        tags = tags[:5]

        return RawEvent(
            external_id=url.rstrip("/").split("/")[-1],
            source=self.source_name,
            title=title,
            description=description[:2000] or title,
            url=url,
            start_datetime=start_dt,
            location_name=location,
            organizer_name=organizer,
            tags=tags,
            is_free=True,
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_date_from_snapshot(text: str) -> datetime | None:
        """Extract start datetime from snapshot patterns like 'Thursday, June 25' + '5:00 PM - 8:00 PM'.

        Search for the time *after* the date match to avoid picking up the navbar clock.
        """
        date_m = re.search(r"\w+day,\s+(\w+ \d{1,2})", text)
        if not date_m:
            return None
        # Search for a time range like "5:00 PM - 8:00 PM" or plain "5:00 PM" after the date
        after_date = text[date_m.start():]
        time_m = re.search(r"(\d{1,2}:\d{2} [AP]M)", after_date)
        if not time_m:
            return None
        try:
            now = datetime.now(timezone.utc)
            year = now.year
            dt = datetime.strptime(f"{date_m.group(1)} {year} {time_m.group(1)}", "%B %d %Y %I:%M %p")
            if dt < now.replace(tzinfo=None) - timedelta(days=14):
                dt = dt.replace(year=year + 1)
            return dt
        except ValueError:
            return None

    @staticmethod
    def _extract_text(tool_result) -> str:
        if hasattr(tool_result, "content"):
            for block in tool_result.content:
                if hasattr(block, "text"):
                    return block.text
        return str(tool_result)

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, AttributeError):
            return None
