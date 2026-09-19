# TULYA v2 backend.  Run from the repo root as `make -C backend <target>`.
# The root Makefile is left alone; these targets live here so the two stacks
# can be driven independently during the migration.
PY ?= python3
SPLIT ?= all

.PHONY: help install migrate migration seed users api test check-stack

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

install:        ## install the production Python stack (sbert, faiss, rapidfuzz, ...)
	pip install -r requirements.txt

migrate:        ## apply database migrations
	alembic upgrade head

migration:      ## autogenerate a migration:  make -C backend migration M="add x"
	alembic revision --autogenerate -m "$(M)"

seed:           ## import the benchmark dataset:  make -C backend seed SPLIT=test
	$(PY) -m app.seed.import_dataset --split $(SPLIT)

users:          ## seed the demo accounts (development only)
	$(PY) -m app.seed.seed_users

api:            ## FastAPI with reload - http://localhost:8000/api/docs
	uvicorn app.main:app --reload --port 8000

test:           ## the backend suite (needs PostgreSQL up and seeded)
	$(PY) -m pytest tests/ -q

check-stack:    ## print which matching backends would actually run; fail if degraded
	@$(PY) -c "from app.matching.backends import resolve_all; \
r = resolve_all(strict=False); print(r.attribution()); \
raise SystemExit(1 if r.degraded else 0)"
