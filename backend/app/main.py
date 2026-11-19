import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_tables
from app.scheduler.jobs import create_scheduler
from app.api import events, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    # On Cloud Run the embedded scheduler is disabled (DISABLE_SCHEDULER=true): the cloud is
    # serve-only. Scraping runs on the Mac via a LaunchAgent, since Luma/Reddit block cloud IPs.
    scheduler = None
    if not settings.disable_scheduler:
        scheduler = create_scheduler()
        scheduler.start()
        admin.set_scheduler(scheduler)
        logger.info("Scheduler started. Next run: %s", scheduler.get_job("nightly_scrape").next_run_time)
    else:
        logger.info("Embedded scheduler disabled (DISABLE_SCHEDULER=true); serve-only mode")
    yield
    if scheduler:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


app = FastAPI(title="Bay Area AI Events Finder", lifespan=lifespan)

_allowed_origins = ["http://localhost:3000", "https://smith.langchain.com"]
if settings.frontend_origin:
    _allowed_origins.append(settings.frontend_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(admin.router)

