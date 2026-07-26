"""Spawn reddit-mcp-server via stdio and dump its tool schemas to disk (deep-agents: raw to disk, trimmed to context)."""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

OUT = "/Users/vinaykumargodavarti/events_finder/.agent/scratch/reddit_mcp_tools.json"


async def main():
    params = StdioServerParameters(command="npx", args=["-y", "reddit-mcp-server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            dump = [
                {"name": t.name, "description": t.description, "inputSchema": t.inputSchema}
                for t in tools.tools
            ]
            with open(OUT, "w") as f:
                json.dump(dump, f, indent=2)
            # Trimmed preview only — full schemas live on disk
            for t in dump:
                req = t["inputSchema"].get("required", [])
                props = list(t["inputSchema"].get("properties", {}).keys())
                print(f"{t['name']}  required={req}  props={props}")


asyncio.run(main())
