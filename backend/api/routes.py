"""
RandomWeb — REST API Routes
Endpoints for random redirect, search, URL submission, and stats.
"""
import logging
import re
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator

from backend.db import (
    get_random_active_url,
    search_websites,
    get_active_count,
    get_total_count,
    url_exists,
)
from backend.workers.validator import enqueue_url

logger = logging.getLogger("randomweb.api")
router = APIRouter(prefix="/api")


# ─── Models ──────────────────────────────────────────────────
class SubmitRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("URL cannot be empty")

        # Add scheme if missing
        if not v.startswith(("http://", "https://")):
            v = f"https://{v}"

        parsed = urlparse(v)
        if not parsed.netloc or "." not in parsed.netloc:
            raise ValueError("Invalid URL format")

        if len(v) > 2000:
            raise ValueError("URL too long")

        return v


class SubmitResponse(BaseModel):
    success: bool
    message: str
    url: str


class RandomResponse(BaseModel):
    url: str


class StatsResponse(BaseModel):
    active_count: int
    total_count: int


class SearchResult(BaseModel):
    url: str
    domain: str
    is_active: bool


# ─── Endpoints ───────────────────────────────────────────────
@router.get("/random", response_model=RandomResponse)
async def get_random():
    """Get a random active website URL for redirect."""
    url = get_random_active_url()
    if not url:
        raise HTTPException(
            status_code=404,
            detail="No active websites found yet. The system is still indexing.",
        )
    return {"url": url}


@router.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
):
    """Search for indexed websites by URL or domain."""
    results = search_websites(q, limit=limit)
    return results


@router.post("/submit", response_model=SubmitResponse)
async def submit_url(request: SubmitRequest):
    """Submit a new URL for validation and indexing."""
    url = request.url
    logger.info("User submitted URL: %s", url)

    # Check if already indexed
    if url_exists(url):
        return SubmitResponse(
            success=True,
            message="This URL is already in our index.",
            url=url,
        )

    # Queue for validation
    await enqueue_url(url, source="user_submit")

    return SubmitResponse(
        success=True,
        message="URL submitted successfully! It will be validated and added if accessible.",
        url=url,
    )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get current index statistics."""
    return StatsResponse(
        active_count=get_active_count(),
        total_count=get_total_count(),
    )


@router.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}
