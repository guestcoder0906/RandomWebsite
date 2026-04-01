"""
WebRoulette — Main Application
FastAPI app with background workers for URL discovery, validation, and re-verification.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.config import SEED_WEBSITES, SUPABASE_URL, SUPABASE_SECRET_KEY
from backend.db import get_client, extract_domain
from backend.workers.validator import run_validator, enqueue_url
from backend.workers.ct_log import run_ct_log_worker
from backend.workers.common_crawl import run_common_crawl_importer
from backend.workers.crawler import run_crawler
from backend.workers.scheduler import run_scheduler
from backend.workers.stats_updater import run_stats_updater

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("webroulette")

# ─── Frontend Path ───────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


async def seed_top_websites():
    """Seed the top 100 websites into the validation queue."""
    logger.info("Seeding %d top websites...", len(SEED_WEBSITES))
    for url in SEED_WEBSITES:
        await enqueue_url(url, source="seed")
    logger.info("All seed websites queued for validation")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage background workers lifecycle."""
    logger.info("=" * 60)
    logger.info("WebRoulette starting up")
    logger.info("Supabase URL: %s", SUPABASE_URL)
    logger.info("Secret key configured: %s", "Yes" if SUPABASE_SECRET_KEY else "No")
    logger.info("=" * 60)

    # Initialize Supabase client
    try:
        get_client()
        logger.info("Supabase client connected")
    except Exception as e:
        logger.error("Failed to connect to Supabase: %s", e)

    # Launch background workers
    tasks = []

    # 1. Validation worker (must start first)
    tasks.append(asyncio.create_task(run_validator(), name="validator"))

    # 2. Seed top websites
    tasks.append(asyncio.create_task(seed_top_websites(), name="seeder"))

    # 3. CT Log worker
    tasks.append(asyncio.create_task(run_ct_log_worker(), name="ct_log"))

    # 4. Common Crawl importer
    tasks.append(asyncio.create_task(run_common_crawl_importer(), name="common_crawl"))

    # 5. BFS Crawler
    tasks.append(asyncio.create_task(run_crawler(), name="crawler"))

    # 6. Re-verification scheduler
    tasks.append(asyncio.create_task(run_scheduler(), name="scheduler"))

    # 7. Stats Updater
    tasks.append(asyncio.create_task(run_stats_updater(), name="stats_updater"))

    logger.info("All %d background workers launched", len(tasks))

    yield

    # Shutdown: cancel all tasks
    logger.info("Shutting down background workers...")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("All workers stopped")


# ─── FastAPI App ─────────────────────────────────────────────
app = FastAPI(
    title="WebRoulette",
    description="Discover random websites from across the internet",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes (MUST be before static files)
app.include_router(router)

# ─── Serve Frontend Static Files ────────────────────────────
if FRONTEND_DIR.exists():
    # Serve index.html for the root path
    @app.get("/")
    async def serve_index():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    # Catch-all: serve static files or fall back to index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve static files or fall back to index.html for SPA routing."""
        file_path = FRONTEND_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIR / "index.html"))

    logger.info("Frontend serving enabled from: %s", FRONTEND_DIR)
else:
    logger.warning("Frontend directory not found at %s", FRONTEND_DIR)
