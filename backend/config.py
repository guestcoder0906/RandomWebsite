"""
RandomWeb — Configuration
Loads environment variables and defines constants for all workers.
"""
import os

# ─── Supabase ────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY", "")

# ─── Crawler Settings ───────────────────────────────────────
USER_AGENT = "RandomWeb/1.0 (+https://github.com/guestcoder0906/RandomWeb; polite-bot)"
REQUEST_TIMEOUT = 10  # seconds
MAX_GLOBAL_CONCURRENCY = 20  # max simultaneous outbound connections
PER_DOMAIN_RATE_LIMIT = 1.0  # requests per second per domain
CRAWL_DELAY_DEFAULT = 1.0  # fallback crawl delay if robots.txt doesn't specify
MAX_CRAWL_DEPTH = 3  # BFS depth limit per seed
MAX_LINKS_PER_PAGE = 50  # max links to extract per page
MAX_QUEUE_SIZE = 100_000  # max URLs in crawler queue

# ─── Validator Settings ──────────────────────────────────────
VALIDATION_BATCH_SIZE = 50  # URLs per validation batch
VALIDATION_CONCURRENCY = 10  # concurrent validation requests
RECHECK_INTERVAL_DAYS = 365  # re-verify every year

# ─── CertStream ──────────────────────────────────────────────
CERTSTREAM_URL = "wss://certstream.calidog.io/"
CT_LOG_BATCH_SIZE = 100  # queue batch size before flushing to validation
CT_LOG_RECONNECT_DELAY = 5  # initial reconnect delay in seconds
CT_LOG_MAX_RECONNECT_DELAY = 300  # max reconnect delay

# ─── Common Crawl ────────────────────────────────────────────
COMMON_CRAWL_INDEX_URL = "https://index.commoncrawl.org/collinfo.json"
COMMON_CRAWL_SAMPLE_SIZE = 10_000  # URLs per crawl import batch
COMMON_CRAWL_RESCAN_HOURS = 168  # re-import weekly (7 * 24)

# ─── Scheduler ───────────────────────────────────────────────
SCHEDULER_INTERVAL_SECONDS = 3600  # run re-verification check every hour
SCHEDULER_BATCH_SIZE = 100  # URLs per re-verification batch

# ─── Blocked TLDs / Patterns ────────────────────────────────
BLOCKED_TLDS = {
    ".local", ".internal", ".test", ".example",
    ".invalid", ".localhost", ".onion",
}

# ─── Top 100 Seed Websites ──────────────────────────────────
SEED_WEBSITES = [
    "https://google.com",
    "https://youtube.com",
    "https://facebook.com",
    "https://instagram.com",
    "https://chatgpt.com",
    "https://x.com",
    "https://reddit.com",
    "https://wikipedia.org",
    "https://whatsapp.com",
    "https://bing.com",
    "https://tiktok.com",
    "https://yahoo.co.jp",
    "https://yandex.ru",
    "https://yahoo.com",
    "https://amazon.com",
    "https://gemini.google.com",
    "https://linkedin.com",
    "https://bet.br",
    "https://baidu.com",
    "https://naver.com",
    "https://netflix.com",
    "https://pinterest.com",
    "https://live.com",
    "https://bilibili.com",
    "https://pornhub.com",
    "https://temu.com",
    "https://dzen.ru",
    "https://office.com",
    "https://microsoft.com",
    "https://xhamster.com",
    "https://twitch.tv",
    "https://xvideos.com",
    "https://canva.com",
    "https://weather.com",
    "https://vk.com",
    "https://globo.com",
    "https://fandom.com",
    "https://news.yahoo.co.jp",
    "https://t.me",
    "https://samsung.com",
    "https://mail.ru",
    "https://duckduckgo.com",
    "https://nytimes.com",
    "https://stripchat.com",
    "https://xnxx.com",
    "https://ebay.com",
    "https://zoom.us",
    "https://xhamster44.desi",
    "https://discord.com",
    "https://eporner.com",
    "https://github.com",
    "https://booking.com",
    "https://spotify.com",
    "https://cricbuzz.com",
    "https://instructure.com",
    "https://docomo.ne.jp",
    "https://roblox.com",
    "https://aliexpress.com",
    "https://bbc.com",
    "https://bbc.co.uk",
    "https://ozon.ru",
    "https://apple.com",
    "https://imdb.com",
    "https://telegram.org",
    "https://brave.com",
    "https://amazon.in",
    "https://chaturbate.com",
    "https://msn.com",
    "https://walmart.com",
    "https://amazon.co.jp",
    "https://paypal.com",
    "https://cnn.com",
    "https://ya.ru",
    "https://indeed.com",
    "https://etsy.com",
    "https://rakuten.co.jp",
    "https://amazon.de",
    "https://espn.com",
    "https://hbomax.com",
    "https://usps.com",
    "https://music.youtube.com",
    "https://ok.ru",
    "https://wildberries.ru",
    "https://office365.com",
    "https://disneyplus.com",
    "https://douyin.com",
    "https://namu.wiki",
    "https://adobe.com",
    "https://shein.com",
    "https://qq.com",
    "https://amazon.co.uk",
    "https://quora.com",
    "https://faphouse.com",
    "https://rutube.ru",
    "https://theguardian.com",
    "https://scribd.com",
    "https://grok.com",
    "https://zillow.com",
    "https://dcinside.com",
    "https://onlyfans.com",
]
