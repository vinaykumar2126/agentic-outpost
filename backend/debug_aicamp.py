"""
Run from backend/ directory:
    python3 debug_aicamp.py
Dumps the raw MCP snapshot from aicamp.ai so we can tune regex patterns.
"""
import asyncio
import re
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

AICAMP_EVENTS_URL = "https://www.aicamp.ai/event/eventsquery?city=US-San+Francisco"
AICAMP_BASE = "https://www.aicamp.ai"


def extract_text(tool_result) -> str:
    if hasattr(tool_result, "content"):
        for block in tool_result.content:
            if hasattr(block, "text"):
                return block.text
    return str(tool_result)


async def main():
    server_params = StdioServerParameters(command="npx", args=["@playwright/mcp", "--headless"])

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("=== Navigating to events listing page ===")
            await session.call_tool("browser_navigate", {"url": AICAMP_EVENTS_URL})
            await asyncio.sleep(3)

            snapshot = await session.call_tool("browser_snapshot", {})
            listing_text = extract_text(snapshot)

            print("\n--- LISTING PAGE SNAPSHOT (first 3000 chars) ---")
            print(listing_text[:3000])

            # Try to find event URLs
            found_ids = re.findall(r"/url:\s+https://www\.aicamp\.ai/event/eventdetails/(\S+)", listing_text)
            print(f"\n=== Found {len(found_ids)} event detail URLs ===")
            for eid in found_ids:
                print(f"  https://www.aicamp.ai/event/eventdetails/{eid}")

            if not found_ids:
                print("\n[!] No URLs matched. Showing all /url: lines for diagnosis:")
                for line in listing_text.splitlines():
                    if "/url:" in line:
                        print(" ", line)
                return

            # Scrape the first event detail page
            first_url = f"{AICAMP_BASE}/event/eventdetails/{found_ids[0]}"
            print(f"\n=== Scraping first event: {first_url} ===")
            await session.call_tool("browser_navigate", {"url": first_url})
            await asyncio.sleep(2)
            detail_snap = await session.call_tool("browser_snapshot", {})
            detail_text = extract_text(detail_snap)

            print("\n--- DETAIL PAGE SNAPSHOT (first 4000 chars) ---")
            print(detail_text[:4000])


asyncio.run(main())
