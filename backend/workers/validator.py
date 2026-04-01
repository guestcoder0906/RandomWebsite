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
    PER_DOMAIN_RATE_LIMIT,
    CRAWL_DELAY_DEFAULT,
    RECHECK_INTERVAL_DAYS,
)
from backend.db import get_client, extract_domain

logger = logging.getLogger("randomweb.validator")

# ─── Shared State ────────────────────────────────────────────
_validation_queue: asyncio.Queue = asyncio.Queue(maxsize=50_000)
_robots_cache: dict[str, Optional[Protego]] = {}
_domain_limiters: dict[str, AsyncLimiter] = {}
_semaphore: Optional[asyncio.Semaphore] = None


def get_validation_queue() -> asyncio.Queue:
    return _validation_queue


async def enqueue_url(url: str, source: str = "unknown"):
    """Add a URL to the validation queue."""
    try:
        _validation_queue.put_nowait({"url": url, "source": source})
    except asyncio.QueueFull:
        logger.warning("Validation queue full, dropping: %s", url)


def _get_domain_limiter(domain: str) -> AsyncLimiter:
    """Get or create a per-domain rate limiter."""
    if domain not in _domain_limiters:
        _domain_limiters[domain] = AsyncLimiter(
            PER_DOMAIN_RATE_LIMIT, 1.0
        )
    return _domain_limiters[domain]


async def _fetch_robots_txt(
    session: aiohttp.ClientSession, domain: str
) -> Optional[Protego]:
    """Fetch and parse robots.txt for a domain. Cached."""
    if domain in _robots_cache:
        return _robots_cache[domain]

    robots_url = f"https://{domain}/robots.txt"
    try:
        async with session.get(
            robots_url,
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
            allow_redirects=True,
            ssl=False,
        ) as resp:
            if resp.status == 200:
                text = await resp.text()
                parser = Protego.parse(text)
                _robots_cache[domain] = parser
                return parser
    except Exception:
        pass

    _robots_cache[domain] = None
    return None


async def _can_fetch(
    session: aiohttp.ClientSession, url: str
) -> tuple[bool, float]:
    """
    Check if we're allowed to fetch a URL per robots.txt.
    Returns (allowed, crawl_delay).
    """
    domain = extract_domain(url)
    robots = await _fetch_robots_txt(session, domain)

    if robots is None:
        return True, CRAWL_DELAY_DEFAULT

    allowed = robots.can_fetch(url, USER_AGENT)
    delay = robots.crawl_delay(USER_AGENT)
    if delay is None:
        delay = CRAWL_DELAY_DEFAULT

    return allowed, delay


async def validate_url(
    session: aiohttp.ClientSession,
    url: str,
    source: str = "unknown",
) -> Optional[dict]:
    """
    Validate a single URL. Returns a record dict if successful, else None.
    Steps:
      1. Check robots.txt
      2. Send HEAD request (fallback to GET)
      3. Return result with status
    """
    domain = extract_domain(url)
    limiter = _get_domain_limiter(domain)

    # Rate limit per domain
    async with limiter:
        # Check robots.txt
        allowed, delay = await _can_fetch(session, url)
        if not allowed:
            logger.debug("Blocked by robots.txt: %s", url)
            return None

        # Respect crawl delay
        if delay > 0:
            await asyncio.sleep(delay)

        now = datetime.now(timezone.utc).isoformat()
        status_code = None

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
            try:
                # Fallback to GET
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    headers={"User-Agent": USER_AGENT},
                    allow_redirects=True,
                    ssl=False,
                ) as resp:
                    status_code = resp.status
            except Exception as e:
                logger.debug("Validation failed for %s: %s", url, e)
                status_code = None

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
                    logger.info("Validating batch of %d URLs", len(batch))
                    records = await _process_batch(session, batch)

                    if records:
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
