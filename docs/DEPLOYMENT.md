# Deploying TULYA

## The error

```
Error: Total bundle size (5715.31 MB) exceeds the maximum function size (500 MB).
```

Vercel found a Python entry point in the repository, installed
`backend/requirements.txt` into a serverless function bundle, and the result was
eleven times the limit.

## Where 5.7 GB came from

One line:

```
torch>=2.2
```

`torch` from the default PyPI index declares the whole CUDA runtime as a hard
dependency. Installing it pulls, before anything of ours is added:

| wheel | size |
|---|---|
| `nvidia-cudnn-cu12` | 773 MB |
| `nvidia-cublas-cu12` | 581 MB |
| `torch` | 555 MB |
| `nvidia-cusparse-cu12` | 366 MB |
| `nvidia-nccl-cu12` | 352 MB |
| `nvidia-cusolver-cu12` | 338 MB |
| `triton` | 248 MB |
| `nvidia-cufft-cu12` | 201 MB |
| **compressed subtotal** | **≈ 3.4 GB** |

Unpacked, that is the 5.7 GB Vercel reported. Every one of those NVIDIA wheels
is GPU code for a service that will never see a GPU. The rest of the stack is
almost free by comparison — faiss-cpu 19 MB, numpy 17 MB, transformers 12 MB,
pandas 11 MB, scikit-learn 9 MB, psycopg 7 MB, rapidfuzz 3 MB.

## Fixing the size does not fix the deployment

Pinning the CPU build removes every NVIDIA wheel and triton:

```
--extra-index-url https://download.pytorch.org/whl/cpu
torch>=2.2
```

That is `backend/requirements-cpu.txt`, and it is worth using on any host —
it cuts the image by roughly an order of magnitude. But it still leaves a few
hundred megabytes of torch plus scipy, scikit-learn and FAISS, which is over
500 MB again, and size was never the real obstacle. Four things make a Vercel
function the wrong target for this particular service:

**The index has to stay in memory.** `IndexFlatIP` is built by loading vectors
and is held in RAM. A serverless function is ephemeral and has no persistent
disk, so every cold start would rebuild the index from scratch before it could
answer anything.

**The model has to load once, not per request.** `all-MiniLM-L6-v2` is ~90 MB
of weights. On Vercel there is no writable filesystem outside `/tmp` and no
warm process to keep them in, so each cold start means fetching from
huggingface.co — which is also a production runtime dependency on the public
internet, and the whole point of the on-premise claim is that there isn't one.

**Execution time.** Index build plus model load against a 10–60 s function
limit is not a margin, it is a coin toss.

**Strict mode will refuse to start anyway.** `MATCHING_STRICT=true` makes
`backends.py` raise rather than fall back to TF-IDF while claiming
Sentence-BERT. So "just drop torch to fit the bundle" produces a service that
correctly refuses to boot. That guarantee is deliberate; do not work around it
by setting `EMBEDDING_BACKEND=tfidf-svd` in production and leaving the deck
claiming Sentence-BERT.

## What to deploy where

| piece | host | why |
|---|---|---|
| Offline steward console | **Vercel** | One self-contained 819 KB HTML file. Static, no build, no runtime. This is what the QR code on the deck points at. |
| FastAPI + matching engine | **Render / Railway / Fly.io / HF Spaces** | Container, no function size cap, warm process holding the model and the FAISS index. |
| PostgreSQL | **Neon / Supabase / Render Postgres** | Managed; set `DATABASE_URL`. |
| Ollama / Llama 3.2 3B | **local only** | 2 GB model, no free tier runs it. The hosted demo uses the rule-based extractor; LLM extraction stays a local capability and is marked PLANNED on the deck. |

## Files added for this

- `vercel.json` — serves `reports/tulya_console.html` as a static site, no build step
- `.vercelignore` — stops Vercel discovering any Python entry point
- `backend/requirements-cpu.txt` — CPU-only torch
- `backend/Dockerfile` — CPU wheels, model baked in at build time, strict mode on,
  runs as a non-root user, health check on `/api/health`
- `.dockerignore`, `render.yaml`

## Deploying the console to Vercel

Root directory is the repository root. Vercel will now build nothing and serve
the console at `/`.

```bash
vercel --prod
```

If the project already has a Root Directory of `backend` set in the dashboard,
clear it first — that setting is why Vercel went looking for
`backend/requirements.txt` in the first place.

## Deploying the backend

```bash
docker build -f backend/Dockerfile -t tulya-api backend/
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg://... \
  -e SECRET_KEY=... \
  tulya-api
```

`render.yaml` does the same on Render. Note `plan: standard` — Sentence-BERT
plus a FAISS index will not fit in a 512 MB instance, and a host that OOM-kills
the process on startup looks identical to a broken build.

**Not verified here.** No Docker daemon was reachable in the environment these
files were written in, and `download.pytorch.org` was blocked, so the image
build and the CPU wheel sizes need confirming on your machine before you rely
on them for the demo.
