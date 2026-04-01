"""
RandomWeb — Common Crawl CDX Importer
Fetches URLs from the Common Crawl CDX Index API to seed the database
with a broad sample of the internet.
"""
import asyncio
import logging
import random
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from backend.config import (
    COMMON_CRAWL_INDEX_URL,
    COMMON_CRAWL_SAMPLE_SIZE,
    COMMON_CRAWL_RESCAN_HOURS,
    USER_AGENT,
    REQUEST_TIMEOUT,
)
from backend.workers.validator import enqueue_url

logger = logging.getLogger("randomweb.common_crawl")

# Sample TLDs to query for broad coverage
SAMPLE_QUERIES = [
    "*.com", "*.org", "*.net", "*.io", "*.co",
    "*.edu", "*.gov", "*.dev", "*.app", "*.info",
    "*.me", "*.tv", "*.co.uk", "*.de", "*.fr",
    "*.jp", "*.ru", "*.br", "*.in", "*.ca",
    "*.au", "*.nl", "*.it", "*.es", "*.ch",
    "*.se", "*.no", "*.fi", "*.dk", "*.pl",
]


async def _get_latest_crawl_index(
    session: aiohttp.ClientSession,
) -> Optional[str]:
    """Fetch the latest Common Crawl index URL."""
    try:
        async with session.get(
            COMMON_CRAWL_INDEX_URL,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            if resp.status != 200:
                logger.error("Failed to fetch crawl index: HTTP %d", resp.status)
                return None

            data = await resp.json()
            if data and len(data) > 0:
                # Latest crawl is first in the list
                cdx_api = data[0].get("cdx-api")
                crawl_id = data[0].get("id", "unknown")
                logger.info("Latest Common Crawl: %s", crawl_id)
                return cdx_api

    except Exception as e:
        logger.error("Failed to get crawl index: %s", e)

    return None


async def _query_cdx_for_domains(
    session: aiohttp.ClientSession,
    cdx_api: str,
    query: str,
    limit: int = 500,
) -> list[str]:
    """Query the CDX API for URLs matching a pattern."""
    urls = []
    try:
        params = {
            "url": query,
            "output": "json",
            "fl": "url",
            "limit": str(limit),
            "filter": "status:200",
        }
        
        async with session.get(
            cdx_api,
            params=params,
            timeout=aiohttp.ClientTimeout(total=60),
            headers={"User-Agent": USER_AGENT},
        ) as resp:
            if resp.status != 200:
                logger.debug("CDX query failed for %s: HTTP %d", query, resp.status)
                return urls

            text = await resp.text()
            lines = text.strip().split("\n")

            for line in lines:
                line = line.strip()
                if not line or line.startswith("["):
                    continue
                try:
                    # Lines can be JSON or plain URL
                    if line.startswith("{"):
                        import json
                        data = json.loads(line)
                        url = data.get("url", "")
                    elif line.startswith('"'):
                        url = line.strip('"')
                    else:
                        url = line
                    
                    if url and url.startswith("http"):
                        # Normalize to homepage
                        parsed = urlparse(url)
                        normalized = f"https://{parsed.netloc}"
                        urls.append(normalized)
                except Exception:
                    continue

    except asyncio.TimeoutError:
        logger.debug("CDX query timed out for %s", query)
    except Exception as e:
        logger.debug("CDX query error for %s: %s", query, e)

    return urls


async def run_common_crawl_importer():
    """
    Main Common Crawl import loop.
    Fetches a broad sample of URLs from the CDX API and queues them.
    Runs once on startup, then rescans weekly.
    """
    logger.info("Common Crawl importer starting")

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                cdx_api = await _get_latest_crawl_index(session)
                if not cdx_api:
                    logger.warning("No CDX API available, retrying in 1 hour")
                    await asyncio.sleep(3600)
                    continue

                logger.info("Importing from CDX API: %s", cdx_api)
                total_queued = 0
                seen_domains = set()

                # Shuffle queries for variety
                queries = SAMPLE_QUERIES.copy()
                random.shuffle(queries)

                per_query_limit = max(
                    50, COMMON_CRAWL_SAMPLE_SIZE // len(queries)
                )

                for query in queries:
                    if total_queued >= COMMON_CRAWL_SAMPLE_SIZE:
                        break

                    urls = await _query_cdx_for_domains(
                        session, cdx_api, query, limit=per_query_limit
                    )

                    for url in urls:
                        domain = urlparse(url).netloc
                        if domain and domain not in seen_domains:
                            seen_domains.add(domain)
                            await enqueue_url(url, source="common_crawl")
                            total_queued += 1

                            if total_queued >= COMMON_CRAWL_SAMPLE_SIZE:
                                break

                    # Be polite to the CDX API
                    await asyncio.sleep(2)

                logger.info(
                    "Common Crawl import complete: %d URLs queued", total_queued
                )

        except Exception as e:
            logger.error("Common Crawl importer error: %s", e)

        # Wait before next rescan
        logger.info(
            "Next Common Crawl rescan in %d hours",
            COMMON_CRAWL_RESCAN_HOURS,
        )
        await asyncio.sleep(COMMON_CRAWL_RESCAN_HOURS * 3600)
