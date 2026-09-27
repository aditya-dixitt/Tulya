# Running the TULYA v2 backend

Phases 2–3 only. Docker Compose arrives in Phase 9; until then this runs
directly against a local PostgreSQL.

## 1. PostgreSQL

```bash
createuser tulya --pwprompt        # password: tulya
createdb tulya -O tulya
```

## 2. Configuration

```bash
cp .env.example .env
# edit DATABASE_URL to point at your instance, e.g.
#   DATABASE_URL=postgresql+psycopg://tulya:tulya@localhost:5432/tulya
```

`SECRET_KEY` has no default; the app will not start without one of at least
32 characters.

## 3. Dependencies

```bash
make -C backend install
```

This pulls `sentence-transformers`, `torch`, `faiss-cpu` and `rapidfuzz` —
the production stack. On first use, `all-MiniLM-L6-v2` (~90 MB) downloads from
Hugging Face; after that everything runs offline.

## 4. Confirm the real stack is what will run

```bash
make -C backend check-stack
```

Expected:

```
encoder=sbert(sentence-transformers/all-MiniLM-L6-v2) index=faiss-flatip fuzzy=rapidfuzz
```

Exits non-zero if any stage fell back. To make that a hard failure at startup
too, set `MATCHING_STRICT=true` — the app then refuses to boot rather than
scoring with TF-IDF while claiming Sentence-BERT.

## 5. Schema and data

```bash
make -C backend migrate
make -C backend seed SPLIT=test      # 6,995 records, ~8s
make -C backend users                # demo accounts, development only
```

`seed` reads `data/out/records.csv` — the existing benchmark dataset. If the
file is missing it fails rather than inventing one.

## 6. Run it

```bash
make -C backend api
```

- API docs: <http://localhost:8000/api/docs>
- Readiness (shows which backends resolved): <http://localhost:8000/api/ready>

Sign in with `steward` / `steward123`, then:

```bash
curl -c /tmp/c -X POST localhost:8000/api/auth/login \
  -H 'content-type: application/json' \
  -d '{"username":"steward","password":"steward123"}'

curl -b /tmp/c 'localhost:8000/api/materials?q=stainless&limit=3'
```

## 7. Tests

```bash
make -C backend test
```

28 tests against real PostgreSQL, including the engine guarantees: the hard-key
veto, UNKNOWN never counting as MATCH, the coverage floor, fraction-bore
distinctness, FAISS exactness, and strict mode refusing to downgrade.
