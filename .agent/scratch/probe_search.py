"""Probe search_reddit output shape. Raw -> .agent/scratch/reddit_raw/, preview -> stdout."""
import asyncio
import json
import pathlib

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAW_DIR = pathlib.Path("/Users/vinaykumargodavarti/events_finder/.agent/scratch/reddit_raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    params = StdioServerParameters(command="npx", args=["-y", "reddit-mcp-server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_reddit",
                {"query": "AI meetup", "subreddit": "bayarea", "sort": "new",
                 "time_filter": "week", "limit": 5},
            )
            text = ""
            for block in result.content:
                if hasattr(block, "text"):
                    text = block.text
                    break
            (RAW_DIR / "probe_ai_meetup_bayarea.txt").write_text(text)
            # Trimmed preview: first 30 lines + count
            lines = text.splitlines()
            print("\n".join(lines[:30]))
            print(f"... [{max(0, len(lines)-30)} more lines, {len(text)} chars total] saved to reddit_raw/")
            # Is it JSON?
            try:
                json.loads(text)
                print("FORMAT: valid JSON")
            except Exception:
                print("FORMAT: not JSON (prose/markdown)")


asyncio.run(main())
