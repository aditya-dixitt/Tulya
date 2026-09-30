# TULYA backend — the real deployment target.
#
# Built here rather than on Vercel because the matching engine needs three
# things a serverless function does not have: a process that stays alive long
# enough to hold a FAISS index in memory, a filesystem to keep the
# Sentence-BERT weights on, and more than 500 MB of room.
#
# The model is baked in at build time. Downloading all-MiniLM-L6-v2 from
# Hugging Face on every cold start would be slow, and would make the service
# depend on huggingface.co being reachable from production at runtime — which
# it may well not be inside a CPSE network.

# ---------- build ----------------------------------------------------------
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /w
COPY requirements.txt requirements-cpu.txt ./

# CPU wheels only. The default index pulls nvidia-cublas, nvidia-cudnn,
# nvidia-cusparse, nvidia-cusolver, nvidia-cufft, nvidia-nccl and triton —
# about 3.4 GB of CUDA runtime for a service that will never see a GPU.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements-cpu.txt

# Warm the model into the image so the container starts without network.
ENV HF_HOME=/opt/models
RUN /opt/venv/bin/python -c "\
from sentence_transformers import SentenceTransformer; \
m = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
assert m.get_sentence_embedding_dimension() == 384, 'unexpected embedding dim'; \
print('model cached, dim', m.get_sentence_embedding_dimension())"

# ---------- runtime --------------------------------------------------------
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 tulya

COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models

ENV PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/models \
    TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    MATCHING_STRICT=true \
    EMBEDDING_BACKEND=sbert \
    VECTOR_INDEX=faiss \
    FUZZY_BACKEND=rapidfuzz

WORKDIR /srv
COPY --chown=tulya:tulya . /srv
USER tulya

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

# One worker. Each worker holds its own copy of the model and the FAISS index,
# so worker count is a memory decision, not a throughput knob — raise it only
# after measuring resident set size on the target host.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
