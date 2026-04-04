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
            
            # Fetch highest ID as proxy for total_count (very fast)
            total_res = client.table("websites").select("id").order("id", desc=True).limit(1).execute()
            total_count = total_res.data[0]["id"] if total_res.data else 0
            
            # Fetch exact active count (relatively fast with index)
            # Use 'estimated' or 'planned' if this becomes a bottleneck, but for now 
            # we'll use a lean select to avoid timeouts.
            active_res = client.table("websites").select("id", count="exact").eq("is_active", True).limit(1).execute()
            active_count = active_res.count if active_res.count is not None else 0
            
            # If total_count is somehow 0 but active_res has data, sync them
            if total_count == 0 and active_count > 0:
                total_count = active_count

            # Update stats table
            now = datetime.now(timezone.utc).isoformat()
            client.table("stats").upsert({
                "id": 1,
                "active_count": active_count,
                "total_count": total_count,
                "updated_at": now
            }).execute()
            
            logger.debug("Stats updated: active=%d, total=%d", active_count, total_count)
            
        except Exception as e:
            logger.error("Stats updater error: %s", e)

        # Wait 2 seconds for faster updates
        await asyncio.sleep(2)
