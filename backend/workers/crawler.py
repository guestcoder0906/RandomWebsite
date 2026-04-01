"""
RandomWeb — BFS Recursive Crawler
Breadth-first crawler that extracts and queues all hyperlinks from indexed pages
to continuously expand the known network graph.
"""
import asyncio
import logging
import re
from collections import deque
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from aiolimiter import AsyncLimiter
from bs4 import BeautifulSoup
from protego import Protego

from backend.config import (
    USER_AGENT,
    REQUEST_TIMEOUT,
    MAX_GLOBAL_CONCURRENCY,
    PER_DOMAIN_RATE_LIMIT,
    CRAWL_DELAY_DEFAULT,
    MAX_CRAWL_DEPTH,
    MAX_LINKS_PER_PAGE,
    MAX_QUEUE_SIZE,
    BLOCKED_TLDS,
)
from backend.workers.validator import enqueue_url
from backend.db import get_client

logger = logging.getLogger("randomweb.crawler")

# ─── State ───────────────────────────────────────────────────
_crawl_queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
_visited: set = set()
_MAX_VISITED_CACHE = 1_000_000
_robots_cache: dict[str, Optional[Protego]] = {}
_domain_limiters: dict[str, AsyncLimiter] = {}

# File extensions to skip
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".mp3", ".mp4", ".avi", ".mkv", ".mov", ".flv",
    ".exe", ".msi", ".dmg", ".apk",
}


def _get_domain_limiter(domain: str) -> AsyncLimiter:
    if domain not in _domain_limiters:
        _domain_limiters[domain] = AsyncLimiter(PER_DOMAIN_RATE_LIMIT, 1.0)
    return _domain_limiters[domain]


async def _fetch_robots(
    session: aiohttp.ClientSession, domain: str
) -> Optional[Protego]:
    if domain in _robots_cache:
        return _robots_cache[domain]

    try:
        async with session.get(
            f"https://{domain}/robots.txt",
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


def _normalize_url(base_url: str, href: str) -> Optional[str]:
    """Normalize and validate a discovered URL."""
    try:
        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # Only HTTP/HTTPS
        if parsed.scheme not in ("http", "https"):
            return None

        # Skip blocked TLDs
        domain = parsed.netloc.lower()
        for tld in BLOCKED_TLDS:
            if domain.endswith(tld):
                return None

        # Skip file extensions we don't want
        path_lower = parsed.path.lower()
        for ext in SKIP_EXTENSIONS:
            if path_lower.endswith(ext):
                return None

        # Strip fragments and normalize
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean += f"?{parsed.query}"

        # Remove trailing slash for consistency
        clean = clean.rstrip("/")

        return clean if len(clean) < 2000 else None

    except Exception:
        return None


async def _crawl_page(
    session: aiohttp.ClientSession,
    url: str,
    depth: int,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    """
    Fetch a page and extract all hyperlinks.
    Returns list of discovered URLs.
    """
    domain = urlparse(url).netloc
    limiter = _get_domain_limiter(domain)

    async with semaphore:
        async with limiter:
            # Check robots.txt
            robots = await _fetch_robots(session, domain)
            if robots and not robots.can_fetch(url, USER_AGENT):
                return []

            # Respect crawl delay
            delay = CRAWL_DELAY_DEFAULT
            if robots:
                d = robots.crawl_delay(USER_AGENT)
                if d is not None:
                    delay = d
            if delay > 0:
                await asyncio.sleep(delay)

            discovered = []
            try:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    headers={
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html",
                    },
                    allow_redirects=True,
                    ssl=False,
                ) as resp:
                    if resp.status != 200:
                        return []

                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" not in content_type:
                        return []

                    # Limit response body to avoid memory issues
                    body = await resp.text(errors="ignore")
                    if len(body) > 5_000_000:  # 5MB limit
                        body = body[:5_000_000]

                    soup = BeautifulSoup(body, "html.parser")
                    links = soup.find_all("a", href=True)

                    count = 0
                    for link in links:
                        if count >= MAX_LINKS_PER_PAGE:
                            break

                        href = link.get("href", "").strip()
                        if not href:
                            continue

                        normalized = _normalize_url(url, href)
                        if normalized and normalized not in _visited:
                            discovered.append(normalized)
                            count += 1

            except asyncio.TimeoutError:
                logger.debug("Timeout crawling %s", url)
            except Exception as e:
                logger.debug("Error crawling %s: %s", url, e)

            return discovered


async def seed_from_database():
    """Load existing active URLs from database as crawler seeds."""
    try:
        result = (
            get_client()
            .table("websites")
            .select("url")
            .eq("is_active", True)
            .limit(1000)
            .execute()
        )
        if result.data:
            for row in result.data:
                url = row["url"]
                if url not in _visited:
                    _crawl_queue.append({"url": url, "depth": 0})
            logger.info("Seeded crawler with %d URLs from database", len(result.data))
    except Exception as e:
        logger.error("Failed to seed from database: %s", e)


async def run_crawler():
    """
    Main BFS crawler loop.
    Continuously crawls pages, extracts links, and queues discoveries
    for validation.
    """
    logger.info("BFS Crawler starting")

    # Wait for initial seeds to be validated
    await asyncio.sleep(30)

    # Seed from database
    await seed_from_database()

    semaphore = asyncio.Semaphore(MAX_GLOBAL_CONCURRENCY)
    connector = aiohttp.TCPConnector(
        limit=MAX_GLOBAL_CONCURRENCY,
        ttl_dns_cache=300,
        force_close=False,
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            try:
                if not _crawl_queue:
                    # Re-seed periodically
                    await seed_from_database()
                    if not _crawl_queue:
                        logger.debug("Crawler queue empty, waiting...")
                        await asyncio.sleep(60)
                        continue

                # Process a batch
                batch_size = min(10, len(_crawl_queue))
                tasks = []

                for _ in range(batch_size):
                    if not _crawl_queue:
                        break

                    item = _crawl_queue.popleft()
                    url = item["url"]
                    depth = item["depth"]

                    if url in _visited:
                        continue
                    _visited.add(url)

                    # Evict old entries from visited cache
                    if len(_visited) > _MAX_VISITED_CACHE:
                        to_remove = list(_visited)[:_MAX_VISITED_CACHE // 2]
                        for v in to_remove:
                            _visited.discard(v)

                    if depth <= MAX_CRAWL_DEPTH:
                        tasks.append(_crawl_page(session, url, depth, semaphore))

                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    for result in results:
                        if isinstance(result, list):
                            for discovered_url in result:
                                # Extract homepage for validation
                                parsed = urlparse(discovered_url)
                                homepage = f"https://{parsed.netloc}"
                                await enqueue_url(homepage, source="crawler")

                                # Add to crawl queue for further BFS
                                if (
                                    len(_crawl_queue) < MAX_QUEUE_SIZE
                                    and discovered_url not in _visited
                                ):
                                    current_depth = 1  # simplified
                                    if current_depth < MAX_CRAWL_DEPTH:
                                        _crawl_queue.append({
                                            "url": discovered_url,
                                            "depth": current_depth + 1,
                                        })

                # Small delay between batches
                await asyncio.sleep(0.5)

            except Exception as e:
                logger.error("Crawler loop error: %s", e)
                await asyncio.sleep(10)
