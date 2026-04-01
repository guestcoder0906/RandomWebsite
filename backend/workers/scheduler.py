"""
RandomWeb — Re-verification Scheduler
Rolling yearly re-verification of indexed websites.
Politely re-checks active URLs and toggles visibility on failure.
"""
import asyncio
import logging
from datetime import datetime, timezone

from backend.config import SCHEDULER_INTERVAL_SECONDS, SCHEDULER_BATCH_SIZE
from backend.db import get_urls_needing_recheck
from backend.workers.validator import enqueue_url

logger = logging.getLogger("randomweb.scheduler")


async def run_scheduler():
    """
    Background scheduler that continuously checks for URLs due re-verification.
    Runs every hour, queries for URLs where next_check <= now(),
    and routes them through the validation queue.
    """
    logger.info("Re-verification scheduler started (interval: %ds)", SCHEDULER_INTERVAL_SECONDS)

    # Initial delay to let the system warm up
    await asyncio.sleep(120)

    while True:
        try:
            urls = get_urls_needing_recheck(limit=SCHEDULER_BATCH_SIZE)

            if urls:
                logger.info("Re-verifying %d URLs", len(urls))
                for record in urls:
                    await enqueue_url(record["url"], source="recheck")
                    # Small delay between queuing to avoid flooding
                    await asyncio.sleep(0.1)

                logger.info("Queued %d URLs for re-verification", len(urls))
            else:
                logger.debug("No URLs due for re-verification")

        except Exception as e:
            logger.error("Scheduler error: %s", e)

        # Wait until next check
        await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)
