"""
The embedding worker (the "cook").

Loop forever:
  1. Take over tickets that another worker took but never finished
     (it probably crashed): XAUTOCLAIM.
  2. Otherwise wait for a new ticket: XREADGROUP.
  3. For each ticket: download image -> CLIP -> save embedding -> XACK.

Guarantees:
- At-least-once: a ticket is only removed (XACK) after the result is saved
  in Postgres. Crash before that and another worker redoes it.
- Idempotent: redoing a job is harmless. An image already "indexed" is skipped.
- Bounded retries: after QUEUE_MAX_ATTEMPTS failures the image is marked
  "failed" and the ticket goes to a dead-letter stream for inspection,
  instead of retrying forever.
- Sweep: images stuck "pending" that never got a ticket (e.g. Redis was
  down during upload) get re-queued.

Run: python -m worker.worker
"""
import logging
import os
import signal
import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select

from api.app import jobs, storage
from api.app.config import get_settings
from api.app.db import SessionLocal
from api.app.models import Image, ImageStatus
from worker.embedder import load_embedder

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")
log = logging.getLogger("worker")

SWEEP_EVERY_SECONDS = 60
QUEUE_BLOCK_MS = 2000  # keep well under the Redis socket_timeout (15 s) in api/app/jobs.py
SWEEP_PENDING_OLDER_THAN = timedelta(minutes=5)

_running = True


def _stop(signum, _frame):
    # docker compose stop sends SIGTERM: finish the current job, then exit.
    global _running
    log.info("Signal %s received, finishing current job then exiting", signum)
    _running = False


def process_image(image_id: uuid.UUID, embedder) -> str:
    """
    Do the work for one image. Returns what happened:
      "indexed" | "skipped" | "missing"
    Raises on failure (caller decides retry vs give up).
    """
    with SessionLocal() as db:
        image = db.get(Image, image_id)
        if image is None:
            return "missing"  # deleted after upload; nothing to do
        if image.status in (ImageStatus.indexed, ImageStatus.failed):
            return "skipped"  # duplicate ticket, already finished: idempotency

        image.status = ImageStatus.processing
        image.attempts += 1
        db.commit()

        data = storage.get_bytes(image.storage_key)
        vector: np.ndarray = embedder.embed(data)

        image.embedding = vector.astype(np.float32).tobytes()
        image.embedding_model = embedder.name
        image.status = ImageStatus.indexed
        image.error = None
        image.indexed_at = datetime.now(timezone.utc)
        db.commit()
        return "indexed"


def record_failure(image_id: uuid.UUID, error: str) -> bool:
    """Save the error. Returns True if the image has used up all its attempts."""
    settings = get_settings()
    with SessionLocal() as db:
        image = db.get(Image, image_id)
        if image is None:
            return True
        image.error = error[:2000]
        give_up = image.attempts >= settings.queue_max_attempts
        image.status = ImageStatus.failed if give_up else ImageStatus.pending
        db.commit()
        return give_up


def handle_ticket(ticket_id: str, fields: dict, embedder) -> None:
    settings = get_settings()
    r = jobs.get_redis()
    ack = lambda: r.xack(settings.queue_stream, settings.queue_group, ticket_id)  # noqa: E731

    try:
        image_id = uuid.UUID(fields["image_id"])
    except (KeyError, ValueError):
        log.error("Malformed ticket %s %r, dropping", ticket_id, fields)
        ack()
        return

    started = time.perf_counter()
    try:
        outcome = process_image(image_id, embedder)
    except Exception as exc:
        log.exception("Image %s failed", image_id)
        if record_failure(image_id, f"{type(exc).__name__}: {exc}"):
            # Out of attempts: park the ticket in the dead-letter stream and stop retrying.
            r.xadd(
                settings.queue_dead_letter_stream,
                {"image_id": str(image_id), "error": str(exc)[:500], "ticket_id": ticket_id},
                maxlen=10_000,
                approximate=True,
            )
            ack()
            log.warning("Image %s marked failed and dead-lettered", image_id)
        # else: no ack. The ticket stays pending and XAUTOCLAIM hands it out
        # again after QUEUE_CLAIM_IDLE_MS, which doubles as a retry delay.
        return

    ack()
    log.info("Image %s -> %s in %.0f ms", image_id, outcome, (time.perf_counter() - started) * 1000)


def sweep_orphans() -> None:
    """Re-queue images that are 'pending', never attempted, and older than 5 minutes."""
    cutoff = datetime.now(timezone.utc) - SWEEP_PENDING_OLDER_THAN
    with SessionLocal() as db:
        ids = db.scalars(
            select(Image.id)
            .where(Image.status == ImageStatus.pending, Image.attempts == 0, Image.created_at < cutoff)
            .limit(100)
        ).all()
    for image_id in ids:
        jobs.enqueue_embedding_job(image_id)
    if ids:
        log.info("Sweep re-queued %d orphaned image(s)", len(ids))


def run() -> None:
    settings = get_settings()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    # Unique name per worker process, so Redis knows who holds which ticket.
    consumer = f"{socket.gethostname()}-{os.getpid()}"

    log.info("Loading embedder %r ...", settings.embedder)
    embedder = load_embedder(settings.embedder, settings.clip_model, settings.clip_pretrained)
    log.info("Embedder ready: %s", embedder.name)

    jobs.ensure_consumer_group()
    r = jobs.get_redis()
    log.info("Worker %s listening on stream %r", consumer, settings.queue_stream)

    last_sweep = 0.0
    while _running:
        try:
            if time.monotonic() - last_sweep > SWEEP_EVERY_SECONDS:
                sweep_orphans()
                last_sweep = time.monotonic()

            # 1. Stuck tickets first (their worker crashed or the job failed earlier).
            _next, tickets, _deleted = r.xautoclaim(
                settings.queue_stream,
                settings.queue_group,
                consumer,
                min_idle_time=settings.queue_claim_idle_ms,
                start_id="0-0",
                count=5,
            )

            # 2. Otherwise new tickets. ">" = never delivered to anyone.
            #    block: wait up to 2 s for one instead of spinning. Kept short so
            #    stuck tickets (step 1) are checked often.
            if not tickets:
                response = r.xreadgroup(
                    settings.queue_group,
                    consumer,
                    {settings.queue_stream: ">"},
                    count=1,
                    block=QUEUE_BLOCK_MS,
                )
                tickets = response[0][1] if response else []

            for ticket_id, fields in tickets:
                if not _running:
                    break
                handle_ticket(ticket_id, fields, embedder)

        except Exception:
            # Redis/Postgres hiccup: wait and try again instead of dying.
            log.exception("Worker loop error, retrying in 3 s")
            time.sleep(3)

    log.info("Worker stopped")


if __name__ == "__main__":
    run()
