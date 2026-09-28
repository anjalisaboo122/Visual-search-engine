import asyncio

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI, Response, status
from minio import Minio

from api.app.auth import router as auth_router
from api.app.config import Settings, get_settings

app = FastAPI(title="Visual Search Engine API")

# Adds /auth/signup, /auth/login, /auth/me
app.include_router(auth_router)


async def check_postgres(settings: Settings) -> bool:
    try:
        conn = await asyncpg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            user=settings.postgres_user,
            password=settings.postgres_password,
            database=settings.postgres_db,
            timeout=3.0,
        )
        try:
            await conn.fetchval("SELECT 1")
            return True
        finally:
            await conn.close()
    except Exception:
        return False


async def check_redis(settings: Settings) -> bool:
    try:
        client = aioredis.from_url(
            settings.redis_url,
            socket_timeout=3.0,
            socket_connect_timeout=3.0,
        )
        try:
            await client.ping()
            return True
        finally:
            await client.aclose()
    except Exception:
        return False


def _check_storage_sync(settings: Settings) -> bool:
    try:
        client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.storage_secure,
        )
        client.list_buckets()
        return True
    except Exception:
        return False


async def check_storage(settings: Settings) -> bool:
    return await asyncio.to_thread(_check_storage_sync, settings)


@app.get("/health")
async def health_check(response: Response):
    settings = get_settings()

    pg_ok, redis_ok, storage_ok = await asyncio.gather(
        check_postgres(settings),
        check_redis(settings),
        check_storage(settings),
    )

    all_healthy = pg_ok and redis_ok and storage_ok
    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if all_healthy else "unhealthy",
        "postgres": "ok" if pg_ok else "unhealthy",
        "redis": "ok" if redis_ok else "unhealthy",
        "storage": "ok" if storage_ok else "unhealthy",
    }
