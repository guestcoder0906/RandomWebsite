"""
WebRoulette — NSFW Domain Filter
Loads a blocklist of ~12K known adult/NSFW domains and provides
fast O(1) lookup to prevent indexing or serving them.

Source: https://github.com/chadmayfield/my-pihole-blocklists
"""
import logging
import os

logger = logging.getLogger("webroulette.nsfw_filter")

# ─── Load Blocklist ─────────────────────────────────────────
_BLOCKLIST_PATH = os.path.join(os.path.dirname(__file__), "nsfw_blocklist.txt")
_blocked_domains: set[str] = set()


def _load_blocklist():
    """Load NSFW domains from the blocklist file into a set for O(1) lookup."""
    global _blocked_domains
    try:
        with open(_BLOCKLIST_PATH, "r") as f:
            for line in f:
                domain = line.strip().lower()
                if domain and not domain.startswith("#"):
                    _blocked_domains.add(domain)
        logger.info("NSFW blocklist loaded: %d domains blocked", len(_blocked_domains))
    except FileNotFoundError:
        logger.warning("NSFW blocklist not found at %s — no filtering active", _BLOCKLIST_PATH)
    except Exception as e:
        logger.error("Failed to load NSFW blocklist: %s", e)


# Load on import
_load_blocklist()


def is_nsfw_domain(domain: str) -> bool:
    """
    Check if a domain (or any of its parent domains) is in the NSFW blocklist.
    
    Examples:
        is_nsfw_domain("pornhub.com")           -> True
        is_nsfw_domain("www.pornhub.com")        -> True
        is_nsfw_domain("sub.xvideos.com")        -> True
        is_nsfw_domain("github.com")             -> False
    """
    if not domain:
        return False

    domain = domain.lower().strip()

    # Direct match
    if domain in _blocked_domains:
        return True

    # Check parent domains (e.g., "www.pornhub.com" -> "pornhub.com")
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in _blocked_domains:
            return True

    return False


def is_nsfw_url(url: str) -> bool:
    """
    Check if a URL points to an NSFW domain.
    Extracts the domain from the URL and checks against the blocklist.
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Strip port if present
        if ":" in domain:
            domain = domain.split(":")[0]
        return is_nsfw_domain(domain)
    except Exception:
        return False


def get_blocked_count() -> int:
    """Return the number of blocked NSFW domains."""
    return len(_blocked_domains)
