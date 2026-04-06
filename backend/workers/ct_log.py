"""
RandomWeb — Certificate Transparency Log Worker
Connects to CertStream WebSocket to discover newly registered domains in real-time.
"""
import asyncio
import json
import logging
from urllib.parse import urlparse

import websockets

from backend.config import (
    CERTSTREAM_URL,
    CT_LOG_BATCH_SIZE,
    CT_LOG_RECONNECT_DELAY,
    CT_LOG_MAX_RECONNECT_DELAY,
    BLOCKED_TLDS,
)
from backend.workers.validator import enqueue_url
from backend.db import url_exists

logger = logging.getLogger("randomweb.ct_log")

# ─── Domain Filtering ───────────────────────────────────────
_seen_domains: set = set()
_MAX_SEEN_CACHE = 500_000



def _is_valid_domain(domain: str) -> bool:
    """Filter out invalid, wildcard, IP, and blocked TLD domains."""
    if not domain or len(domain) < 4:
        return False

    # Skip wildcards
    if domain.startswith("*."):
        domain = domain[2:]
    if "*" in domain:
        return False

    # Skip IP addresses
    parts = domain.split(".")
    if all(p.isdigit() for p in parts):
        return False

    # Skip blocked TLDs
    for tld in BLOCKED_TLDS:
        if domain.endswith(tld):
            return False

    # Must have at least one dot
    if "." not in domain:
        return False

    # Skip overly long domains (likely garbage)
    if len(domain) > 253:
        return False

    return True


def _deduplicate(domain: str) -> bool:
    """Returns True if the domain is new (not seen before)."""
    global _seen_domains
    if domain in _seen_domains:
        return False

    # Evict oldest entries if cache is full
    if len(_seen_domains) >= _MAX_SEEN_CACHE:
        # Remove half the cache (FIFO approximation)
        to_remove = list(_seen_domains)[:_MAX_SEEN_CACHE // 2]
        for d in to_remove:
            _seen_domains.discard(d)

    _seen_domains.add(domain)
    return True


async def _process_message(message: dict):
    """Process a single CertStream message and extract domains."""
    try:
        msg_type = message.get("message_type")
        if msg_type != "certificate_update":
            return

        data = message.get("data", {})
        leaf_cert = data.get("leaf_cert", {})
        all_domains = leaf_cert.get("all_domains", [])

        for domain in all_domains:
            # Strip wildcard prefix
            if domain.startswith("*."):
                domain = domain[2:]

            domain = domain.lower().strip()

            if not _is_valid_domain(domain):
                continue

            if not _deduplicate(domain):
                continue

            url = f"https://{domain}"
            await enqueue_url(url, source="ct_log")

    except Exception as e:
        logger.debug("Error processing CT message: %s", e)


async def run_ct_log_worker():
    """
    Main CT log worker loop. Connects to CertStream WebSocket,
    parses certificate updates, and queues new domains for validation.
    Auto-reconnects with exponential backoff.
    """
    logger.info("CT Log worker starting — connecting to %s", CERTSTREAM_URL)
    reconnect_delay = CT_LOG_RECONNECT_DELAY

    while True:
        try:
            async with websockets.connect(
                CERTSTREAM_URL,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
                max_size=2**20,  # 1MB max message size
            ) as ws:
                logger.info("Connected to CertStream")
                reconnect_delay = CT_LOG_RECONNECT_DELAY  # Reset on success

                async for raw_message in ws:
                    try:
                        message = json.loads(raw_message)
                        await _process_message(message)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        logger.debug("Message processing error: %s", e)

        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("CertStream connection closed: %s", e)
        except Exception as e:
            logger.warning("CertStream connection error: %s", e)

        # Exponential backoff reconnect
        logger.info("Reconnecting to CertStream in %ds...", reconnect_delay)
        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(reconnect_delay * 2, CT_LOG_MAX_RECONNECT_DELAY)
