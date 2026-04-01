"""
RandomWeb — Database Helpers
Supabase client initialization and common query functions.
"""
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import Optional

from supabase import create_client, Client

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SECRET_KEY,
    SUPABASE_PUBLISHABLE_KEY,
    RECHECK_INTERVAL_DAYS,
)

logger = logging.getLogger("randomweb.db")

# ─── Client Initialization ──────────────────────────────────
_client: Optional[Client] = None


def get_client() -> Client:
    """Return a Supabase client using the secret key if available, else publishable."""
    global _client
    if _client is None:
        # Priority: Secret Key (for writes) -> Publishable Key (fallback)
        key = SUPABASE_SECRET_KEY or SUPABASE_PUBLISHABLE_KEY
        
        if not key:
            logger.critical("❌ No Supabase API key found!")
            raise ValueError("SUPABASE_SECRET_KEY and SUPABASE_PUBLISHABLE_KEY are both empty.")
            
        _client = create_client(SUPABASE_URL, key)
        
        # Identify key type for debugging purposes
        key_type = "Managed (New)" if key.startswith("sb_") else "Legacy (JWT)"
        logger.info("✅ Supabase client initialized (Type: %s) for %s", key_type, SUPABASE_URL)
        
    return _client


def extract_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


# ─── Insert / Upsert ────────────────────────────────────────
def upsert_website(
    url: str,
    source: str = "unknown",
    status: Optional[int] = None,
    is_active: bool = False,
) -> bool:
    """Insert or update a website record. Returns True on success."""
    try:
        domain = extract_domain(url)
        now = datetime.now(timezone.utc).isoformat()
        next_check = (
            (datetime.now(timezone.utc) + timedelta(days=RECHECK_INTERVAL_DAYS)).isoformat()
            if is_active
            else None
        )

        data = {
            "url": url,
            "domain": domain,
            "source": source,
            "status": status,
            "is_active": is_active,
            "last_checked": now,
            "next_check": next_check,
        }

        get_client().table("websites").upsert(
            data, on_conflict="url"
        ).execute()
        return True
    except Exception as e:
        logger.error("Failed to upsert %s: %s", url, e)
        return False


def bulk_upsert_websites(records: list[dict]) -> int:
    """Bulk upsert a list of website records. Returns count of successful inserts."""
    if not records:
        return 0
    try:
        get_client().table("websites").upsert(
            records, on_conflict="url"
        ).execute()
        return len(records)
    except Exception as e:
        logger.error("Bulk upsert failed (%d records): %s", len(records), e)
        return 0


# ─── Queries ─────────────────────────────────────────────────
def get_random_active_url() -> Optional[str]:
    """Retrieve a random active website URL using the database function."""
    try:
        result = get_client().rpc("get_random_active_website").execute()
        if result.data and len(result.data) > 0:
            return result.data[0]["url"]
        return None
    except Exception as e:
        logger.error("Failed to get random URL: %s", e)
        return None


def search_websites(query: str, limit: int = 20) -> list[dict]:
    """Search websites by URL or domain using trigram similarity."""
    try:
        result = (
            get_client()
            .table("websites")
            .select("url, domain, is_active")
            .or_(f"url.ilike.%{query}%,domain.ilike.%{query}%")
            .eq("is_active", True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("Search failed for '%s': %s", query, e)
        return []


def get_active_count() -> int:
    """Get the current active website count from stats."""
    try:
        result = get_client().table("stats").select("active_count").eq("id", 1).execute()
        if result.data:
            return result.data[0]["active_count"]
        return 0
    except Exception as e:
        logger.error("Failed to get active count: %s", e)
        return 0


def get_total_count() -> int:
    """Get total indexed websites from stats."""
    try:
        result = get_client().table("stats").select("total_count").eq("id", 1).execute()
        if result.data:
            return result.data[0]["total_count"]
        return 0
    except Exception as e:
        logger.error("Failed to get total count: %s", e)
        return 0


def url_exists(url: str) -> bool:
    """Check if a URL is already in the database."""
    try:
        result = (
            get_client()
            .table("websites")
            .select("id")
            .eq("url", url)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception as e:
        logger.error("Failed to check URL existence: %s", e)
        return False


def get_urls_needing_recheck(limit: int = 100) -> list[dict]:
    """Get URLs that are due for re-verification."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        result = (
            get_client()
            .table("websites")
            .select("id, url, domain")
            .eq("is_active", True)
            .lte("next_check", now)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error("Failed to get recheck URLs: %s", e)
        return []
