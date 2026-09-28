"""
The job queue: a Redis Stream (the "ticket rail").

API side:    enqueue_embedding_job(image_id)  -> adds a ticket
Worker side: reads tickets as part of a "consumer group" (see worker/worker.py)

Why a Stream and not a plain list?
- A plain list pop removes the ticket forever. If the worker crashes
  mid-job, the job is lost.
- A Stream + consumer group keeps every ticket "pending" until a worker
  says "done" (XACK). Tickets from a crashed worker can be taken over
  by another worker (XAUTOCLAIM). Nothing gets lost.
"""
import uuid
from functools import lru_cache

import redis

from api.app.config import get_settings


@lru_cache
def get_redis() -> redis.Redis:
    settings = get_settings()
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        decode_responses=True,
        # Must be LONGER than the worker's blocking wait (QUEUE_BLOCK_MS), or the
        # client gives up mid-wait and the connection gets stuck.
        socket_timeout=15,
        socket_connect_timeout=5,
    )


def ensure_consumer_group() -> None:
    """Create the stream and the consumer group once. Safe to call repeatedly."""
    settings = get_settings()
    try:
        # id="0": the group starts from the beginning of the stream.
        # mkstream=True: create the stream if it doesn't exist yet.
        get_redis().xgroup_create(settings.queue_stream, settings.queue_group, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):  # BUSYGROUP = group already exists, fine
            raise


def enqueue_embedding_job(image_id: uuid.UUID) -> str:
    """Add a ticket. Returns the ticket id Redis assigned, e.g. '1727600000000-0'."""
    settings = get_settings()
    return get_redis().xadd(
        settings.queue_stream,
        {"image_id": str(image_id)},
        # Keep the stream from growing forever: trim to ~100k entries.
        maxlen=100_000,
        approximate=True,
    )
