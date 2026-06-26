import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import create_tables
from app.scheduler.jobs import create_scheduler
from app.api import events, admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    scheduler = create_scheduler()
    scheduler.start()
    admin.set_scheduler(scheduler)
    logger.info("Scheduler started. Next run: %s", scheduler.get_job("nightly_scrape").next_run_time)
    yield
    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="Bay Area AI Events Finder", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(admin.router)
