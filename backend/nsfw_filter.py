"""
WebRoulette — NSFW Domain Filter (Multi-Layer)
Provides comprehensive adult content filtering through:
  1. Domain blocklist (~12K known adult domains)
  2. NSFW keyword detection in domains and URLs
  3. Adult content meta-tag detection during page validation

Source: https://github.com/chadmayfield/my-pihole-blocklists
"""
import logging
import os
import re

logger = logging.getLogger("webroulette.nsfw_filter")

# ─── Layer 1: Domain Blocklist ──────────────────────────────
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


# ─── Layer 2: NSFW Keyword Detection ────────────────────────
# Explicit keywords that indicate adult content when found in domain names.
# These are checked as whole-word boundaries to avoid false positives
# (e.g., "essex.com" won't match "sex").
_NSFW_EXACT_KEYWORDS = {
    "porn", "porno", "pornos", "porno",
    "xxx", "xxxx",
    "hentai",
    "xnxx", "xvideos", "xhamster",
    "brazzers", "bangbros",
    "onlyfans",
    "chaturbate", "livejasmin",
    "redtube", "youporn",
    "milf", "milfs",
    "camgirl", "camgirls",
    "jizz",
    "bukkit",
    "faphouse",
    "stripchat",
    "nsfw",
    "r18", "r-18",
}

# Substrings that are strong NSFW signals even as partial matches
_NSFW_SUBSTRING_PATTERNS = [
    "pornhub", "porntube", "pornstar",
    "sexcam", "sextube", "sexvideo", "sexchat",
    "livesex", "freesex", "hotsex",
    "adultvideo", "adultcam", "adultchat",
    "webcamgirl", "webcamsex",
    "nudevideo", "nudecam",
    "escortservice", "escortgirl",
    "hentaivideo", "hentaistream",
    "xxxvideo", "xxxcam", "xxxlive",
    "camwhore", "camslut",
    "freeporns", "freeporn",
    "teenporns", "teenporn",
]

# Compile a regex for efficient substring matching
_NSFW_SUBSTRING_RE = re.compile(
    "|".join(re.escape(p) for p in _NSFW_SUBSTRING_PATTERNS),
    re.IGNORECASE,
)


def _has_nsfw_keywords(domain: str) -> bool:
    """
    Check if a domain contains NSFW keywords.
    Uses word-boundary matching for exact keywords to reduce false positives.
    """
    domain_lower = domain.lower()

    # Remove TLD for keyword analysis (e.g., "freeporn.com" -> "freeporn")
    name_part = domain_lower.rsplit(".", 1)[0] if "." in domain_lower else domain_lower

    # Split on common separators (dots, hyphens, underscores)
    words = set(re.split(r"[.\-_]", name_part))

    # Check exact keyword matches (word-level)
    if words & _NSFW_EXACT_KEYWORDS:
        return True

    # Check substring patterns (catches compound words like "freepornvideo")
    if _NSFW_SUBSTRING_RE.search(name_part):
        return True

    return False


# ─── Layer 3: Content Meta-Tag Detection ────────────────────
# HTML meta tags and headers that indicate adult content
_ADULT_META_PATTERNS = [
    re.compile(r'<meta\s+name=["\']rating["\']\s+content=["\'](?:adult|mature|RTA-5042-1996-1400-1577-RTA)["\']', re.IGNORECASE),
    re.compile(r'<meta\s+content=["\'](?:adult|mature|RTA-5042-1996-1400-1577-RTA)["\']\s+name=["\']rating["\']', re.IGNORECASE),
    re.compile(r'<meta\s+name=["\']RATING["\']\s+content=["\']RTA', re.IGNORECASE),
]


def has_adult_meta_tags(html_content: str) -> bool:
    """
    Check if HTML content contains adult content rating meta tags.
    These are standard tags used by adult sites for content classification:
      - <meta name="rating" content="adult">
      - <meta name="rating" content="RTA-5042-1996-1400-1577-RTA">
    
    Only checks the first 5000 chars (meta tags are always in <head>).
    """
    if not html_content:
        return False

    # Only check the head section (first 5000 chars is plenty)
    head = html_content[:5000]

    for pattern in _ADULT_META_PATTERNS:
        if pattern.search(head):
            return True

    return False


# ─── Public API ─────────────────────────────────────────────
def is_nsfw_domain(domain: str) -> bool:
    """
    Multi-layer NSFW domain check:
      1. Exact match against 12K+ domain blocklist
      2. Parent domain matching (www.pornhub.com -> pornhub.com)
      3. NSFW keyword detection in domain name
    
    Examples:
        is_nsfw_domain("pornhub.com")           -> True  (blocklist)
        is_nsfw_domain("www.pornhub.com")        -> True  (parent match)
        is_nsfw_domain("free-porn-videos.xyz")   -> True  (keyword)
        is_nsfw_domain("my-xxx-site.net")        -> True  (keyword)
        is_nsfw_domain("github.com")             -> False
    """
    if not domain:
        return False

    domain = domain.lower().strip()

    # Layer 1: Direct blocklist match
    if domain in _blocked_domains:
        return True

    # Layer 2: Parent domain matching (e.g., "www.pornhub.com" -> "pornhub.com")
    parts = domain.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[i:])
        if parent in _blocked_domains:
            return True

    # Layer 3: NSFW keyword detection
    if _has_nsfw_keywords(domain):
        return True

    return False


def is_nsfw_url(url: str) -> bool:
    """
    Check if a URL points to an NSFW domain.
    Extracts the domain from the URL and checks against all filters.
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
    """Return the number of blocked NSFW domains in the blocklist."""
    return len(_blocked_domains)
