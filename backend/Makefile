.PHONY: dev test test-one scrape rank install

install:
	pip3 install -r requirements.txt -r requirements-dev.txt

dev:
	uvicorn app.main:app --reload --port 8000

test:
	python3 -m pytest tests/ -v

test-one:
	python3 -m pytest $(TEST) -v

scrape:
	python3 -c "from app.scheduler.jobs import nightly_scrape_job; nightly_scrape_job()"

rank:
	python3 -c "\
from app.database import SessionLocal, create_tables; \
from app.ranking.event_ranker import EventRanker; \
create_tables(); \
db = SessionLocal(); \
n = EventRanker().rank_unscored(db); \
db.close(); \
print(f'Ranked {n} events')"



