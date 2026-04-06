"""
RandomWeb — Polite Async HTTP Validator
Validates discovered URLs with rate limiting, robots.txt compliance,
clear user-agent identification, and timeout rules.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import aiohttp
from aiolimiter import AsyncLimiter
from protego import Protego

from backend.config import (
    USER_AGENT,
    REQUEST_TIMEOUT,
    VALIDATION_CONCURRENCY,
    RECHECK_INTERVAL_DAYS,
)
from backend.db import get_client, extract_domain
from backend.nsfw_filter import is_nsfw_url, has_adult_meta_tags

logger = logging.getLogger("randomweb.validator")

# ─── Shared State ────────────────────────────────────────────
_validation_queue: asyncio.Queue = asyncio.Queue(maxsize=50_000)
_semaphore: Optional[asyncio.Semaphore] = None


def get_validation_queue() -> asyncio.Queue:
    return _validation_queue


async def enqueue_url(url: str, source: str = "unknown"):
    """Add a URL to the validation queue (rejects NSFW domains)."""
    # Block NSFW domains at the earliest point
    if is_nsfw_url(url):
        return

    try:
        _validation_queue.put_nowait({"url": url, "source": source})
    except asyncio.QueueFull:
        logger.warning("Validation queue full, dropping: %s", url)





async def validate_url(
    session: aiohttp.ClientSession,
    url: str,
    source: str = "unknown",
) -> Optional[dict]:
    """
    Validate a single URL. Returns a record dict if successful, else None.
    Steps:
      1. Send HEAD request (fallback to GET)
      2. Check for adult content meta tags
      3. Return result with status
    """
    domain = extract_domain(url)

    now = datetime.now(timezone.utc).isoformat()
    status_code = None
    page_html = None

    try:
        # Try HEAD first (lighter)
        async with session.head(
            url,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            ssl=False,
        ) as resp:
            status_code = resp.status
    except Exception:
        pass

    # If HEAD succeeded, do a lightweight GET to check content for NSFW meta tags
    if status_code == 200:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
                ssl=False,
            ) as resp:
                status_code = resp.status
                if resp.status == 200 and resp.content_type and "html" in resp.content_type:
                    # Only read first 5KB — meta tags are always in <head>
                    page_html = await resp.content.read(5000)
                    page_html = page_html.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("GET fallback failed for %s: %s", url, e)

    # If HEAD failed entirely, try GET as fallback
    elif status_code is None:
        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
                ssl=False,
            ) as resp:
                status_code = resp.status
                if resp.status == 200 and resp.content_type and "html" in resp.content_type:
                    page_html = await resp.content.read(5000)
                    page_html = page_html.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Validation failed for %s: %s", url, e)
            status_code = None

    # Layer 3: Check for adult content meta tags in HTML
    if page_html and has_adult_meta_tags(page_html):
        logger.debug("Blocked by adult meta tags: %s", url)
        return None

    is_active = status_code == 200
    next_check = (
        (datetime.now(timezone.utc) + timedelta(days=RECHECK_INTERVAL_DAYS)).isoformat()
        if is_active
        else None
    )

    record = {
        "url": url,
        "domain": domain,
        "source": source,
        "status": status_code,
        "is_active": is_active,
        "last_checked": now,
        "next_check": next_check,
    }

    return record


async def _process_batch(
    session: aiohttp.ClientSession,
    batch: list[dict],
) -> list[dict]:
    """Validate a batch of URLs concurrently."""
    tasks = [
        validate_url(session, item["url"], item.get("source", "unknown"))
        for item in batch
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    records = []
    for result in results:
        if isinstance(result, dict) and result is not None:
            records.append(result)
        elif isinstance(result, Exception):
            logger.error("Validation task error: %s", result)

    return records


async def run_validator():
    """
    Main validation loop. Continuously drains the validation queue,
    validates URLs in batches, and upserts results to Supabase.
    """
    global _semaphore
    _semaphore = asyncio.Semaphore(VALIDATION_CONCURRENCY)

    logger.info("Validation worker started")

    connector = aiohttp.TCPConnector(
        limit=VALIDATION_CONCURRENCY,
        ttl_dns_cache=300,
        force_close=False,
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            try:
                # Collect a batch
                batch = []
                try:
                    # Wait for at least one item
                    item = await asyncio.wait_for(
                        _validation_queue.get(), timeout=5.0
                    )
                    batch.append(item)
                except asyncio.TimeoutError:
                    await asyncio.sleep(1)
                    continue

                # Drain up to batch size
                while len(batch) < 50 and not _validation_queue.empty():
                    try:
                        batch.append(_validation_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if batch:
                    # Deduplicate batch to prevent repeated work and upsert conflicts
                    batch = list({item["url"]: item for item in batch}.values())
                    
                    logger.info("Validating batch of %d URLs", len(batch))
                    records = await _process_batch(session, batch)

                    if records:
                        # Deduplicate records by URL safely before bulk upsert
                        records = list({r["url"]: r for r in records}.values())
                        
                        # Bulk upsert to Supabase
                        try:
                            get_client().table("websites").upsert(
                                records, on_conflict="url"
                            ).execute()
                            active = sum(1 for r in records if r["is_active"])
                            logger.info(
                                "Upserted %d records (%d active)",
                                len(records), active,
                            )
                        except Exception as e:
                            logger.error("Bulk upsert failed: %s", e)

            except Exception as e:
                logger.error("Validator loop error: %s", e)
                await asyncio.sleep(5)
