import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScrapeRun
from app.schemas import HealthResponse, ScrapeRunSchema, TriggerResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger(__name__)

# Set by main.py after scheduler is created
_scheduler = None


def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler


@router.post("/scrape/trigger", response_model=TriggerResponse)
def trigger_scrape(
    source: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    from app.scheduler.jobs import nightly_scrape_job

    sources = [source] if source else list(_get_active_source_names())
    background_tasks.add_task(nightly_scrape_job, source)
    logger.info("Manual scrape triggered for sources: %s", sources)
    return TriggerResponse(status="started", sources=sources)


@router.get("/scrape/runs", response_model=list[ScrapeRunSchema])
def list_scrape_runs(limit: int = 20, db: Session = Depends(get_db)):
    runs = (
        db.query(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [ScrapeRunSchema.model_validate(r) for r in runs]


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    db_ok = "ok"
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_ok = "error"

    scheduler_status = "stopped"
    next_run = None
    if _scheduler and _scheduler.running:
        scheduler_status = "running"
        job = _scheduler.get_job("nightly_scrape")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return HealthResponse(
        status="ok" if db_ok == "ok" else "degraded",
        db=db_ok,
        scheduler=scheduler_status,
        next_run=next_run,
    )


def _get_active_source_names() -> list[str]:
    try:
        from app.connectors.registry import get_active_connectors
        return [c.source_name for c in get_active_connectors()]
    except Exception:
        return []
