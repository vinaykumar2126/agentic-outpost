# SOURCES.md

## Add more features
 ** Add a new event connector for aicamp.ai that scrapes events using the existing MCP Playwright setup — the same pattern as LumaConnector in luma.py. The connector should:

    - Navigate to https://www.aicamp.ai/ and discover event listing pages
    - Collect individual event URLs by parsing the MCP accessibility tree snapshot
    - Visit each event detail page and extract: title, date/time, location, description, organizer, and URL
    - Return a list of RawEvent objects (same schema as Luma)
    - Be registered in registry.py so it's picked up automatically by the scheduler and ranker

If you get any doubt pls look at CLAUDE.md and FLOW.md from the root of the project. If you still have any questions pls fell free to ask me.