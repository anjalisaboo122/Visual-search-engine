# Visual Search Engine
A backend system where users upload images and find visually similar ones.

## Architecture
- api/: FastAPI service (auth, upload, search endpoints)
- worker/: background worker that computes CLIP embeddings (later)
- shard/: vector index shard services using FAISS (later)
- Postgres: users + image metadata
- MinIO (S3-compatible): image file storage
- Redis: job queue (Redis Streams) + cache

## Rules for the AI agent
- Python 3.12, dependencies managed with uv
- Windows host, PowerShell. Everything runs in Docker Compose
- Work on ONE step at a time, only what I ask for
- Keep code simple and readable; I must be able to explain every line
- Do NOT implement worker logic, sharding, or search merging — I write those myself
- Never hardcode secrets; use .env (and commit .env.example only)
