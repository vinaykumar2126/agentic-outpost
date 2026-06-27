# SOURCES.md

## Add more features
 ** Add a new event connector for aicamp.ai that scrapes events using the existing MCP Playwright setup — the same pattern as LumaConnector in luma.py. The connector should:

    - Navigate to https://www.aicamp.ai/ and discover event listing pages
    - Collect individual event URLs by parsing the MCP accessibility tree snapshot
    - Visit each event detail page and extract: title, date/time, location, description, organizer, and URL
    - Return a list of RawEvent objects (same schema as Luma)
    - Be registered in registry.py so it's picked up automatically by the scheduler and ranker

 ** After the nightly cron job completes successfully, send a summary email to godavartivinaykumar@gmail.com with the day's newly scraped and ranked events.

    The email should:

    Only include new or updated events from that night's run (not the full DB)
    Show events sorted by relevance score (highest first)
    Include for each event: title, score, date, location, organizer, and URL
    Only send if there are events with a score ≥ 7 (no email if nothing interesting was found)
    Be triggered at the end of nightly_scrape_job() in jobs.py, after ranking completes
    I've the gmail mcp server you can check it out


If you get any doubt pls look at CLAUDE.md and FLOW.md from the root of the project. If you still have any questions pls fell free to ask me.
