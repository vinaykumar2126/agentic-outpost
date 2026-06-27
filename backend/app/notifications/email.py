import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Event

logger = logging.getLogger(__name__)

_TO = "godavartivinaykumar@gmail.com"
_MIN_SCORE = 5.0


def send_scrape_summary(db: Session, job_started_at: datetime) -> None:
    """Send a digest email of high-scoring events fetched in this scrape run.
    Skips silently if no events scored >= 7, or if Gmail credentials are not configured.
    Never raises — email failure must not affect the scrape run status.
    """
    if not settings.gmail_user or not settings.gmail_app_password:
        logger.info("Gmail credentials not configured — skipping email summary")
        return

    try:
        events = (
            db.query(Event)
            .filter(
                Event.fetched_at >= job_started_at,
                Event.relevance_score >= _MIN_SCORE,
            )
            .order_by(Event.relevance_score.desc())
            .all()
        )

        if not events:
            logger.info("No events scored >= %.1f in this run — skipping email", _MIN_SCORE)
            return

        body = _format_body(events)
        subject = f"Bay Area AI Events — {len(events)} new event{'s' if len(events) != 1 else ''} worth checking out"

        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = settings.gmail_user
        msg["To"] = _TO

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.gmail_user, settings.gmail_app_password)
            smtp.sendmail(settings.gmail_user, _TO, msg.as_string())

        logger.info("Sent scrape summary email: %d events to %s", len(events), _TO)

    except Exception as exc:
        logger.error("Failed to send scrape summary email: %s", exc)


def _format_body(events: list[Event]) -> str:
    divider = "─" * 50
    lines = [
        f"Found {len(events)} event{'s' if len(events) != 1 else ''} scored {_MIN_SCORE}+ from tonight's scrape:\n"
    ]

    for e in events:
        date_str = e.start_datetime.strftime("%b %d, %Y  %I:%M %p") if e.start_datetime else "TBD"
        lines += [
            divider,
            f"[{e.relevance_score:.1f}]  {e.title}",
            f"Date:       {date_str}",
            f"Location:   {e.location_name or '—'}",
            f"Organizer:  {e.organizer_name or '—'}",
            f"URL:        {e.url}",
        ]
        if e.relevance_justification:
            lines.append(f"Why:        {e.relevance_justification}")
        lines.append("")

    lines.append(divider)
    lines.append("\nHappy networking! 🤖")
    return "\n".join(lines)
