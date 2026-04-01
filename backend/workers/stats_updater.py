"""
RandomWeb — Stats Updater
Continuously updates the stats table every 5 seconds
with the exact count to prevent trigger-induced locking during ingestion.
"""
import asyncio
import logging
from datetime import datetime, timezone

from backend.db import get_client

logger = logging.getLogger("randomweb.stats")

async def run_stats_updater():
    """
    Background worker that updates the live stats every 5 seconds.
    This avoids slow Postgres triggers on the websites table.
    """
    logger.info("Stats updater started (interval: 5s)")

    while True:
        try:
            client = get_client()
            
            # Fetch exact counts
            active_res = client.table("websites").select("*", count="exact").eq("is_active", True).limit(1).execute()
            total_res = client.table("websites").select("*", count="exact").limit(1).execute()
            
            active_count = active_res.count if active_res.count is not None else 0
            total_count = total_res.count if total_res.count is not None else 0
            
            # Update stats table
            now = datetime.now(timezone.utc).isoformat()
            client.table("stats").upsert({
                "id": 1,
                "active_count": active_count,
                "total_count": total_count,
                "updated_at": now
            }).execute()
            
        except Exception as e:
            logger.error("Stats updater error: %s", e)

        # Wait 5 seconds
        await asyncio.sleep(5)
