-- ============================================================
-- RandomWeb — Supabase Schema
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- 1. WEBSITES TABLE
-- ============================================================
CREATE TABLE IF NOT EXISTS websites (
  id           BIGSERIAL PRIMARY KEY,
  url          TEXT NOT NULL UNIQUE,
  domain       TEXT NOT NULL,
  source       TEXT NOT NULL DEFAULT 'unknown',
  status       INTEGER,
  is_active    BOOLEAN NOT NULL DEFAULT false,
  first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_checked TIMESTAMPTZ,
  next_check   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_websites_is_active ON websites (is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_websites_domain ON websites (domain);
CREATE INDEX IF NOT EXISTS idx_websites_next_check ON websites (next_check) WHERE next_check IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_websites_random ON websites (id) WHERE is_active = true;

-- Trigram index for fuzzy search
CREATE INDEX IF NOT EXISTS idx_websites_url_trgm ON websites USING gin (url gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_websites_domain_trgm ON websites USING gin (domain gin_trgm_ops);

-- ============================================================
-- 2. STATS TABLE (single-row, live counter)
-- ============================================================
CREATE TABLE IF NOT EXISTS stats (
  id           INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  active_count BIGINT NOT NULL DEFAULT 0,
  total_count  BIGINT NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO stats (active_count, total_count) VALUES (0, 0)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 3. TRIGGER — Auto-update stats on website changes
-- ============================================================
CREATE OR REPLACE FUNCTION update_stats_count()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE stats SET
    active_count = (SELECT count(*) FROM websites WHERE is_active = true),
    total_count  = (SELECT count(*) FROM websites),
    updated_at   = now()
  WHERE id = 1;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_stats ON websites;
CREATE TRIGGER trg_update_stats
  AFTER INSERT OR UPDATE OF is_active OR DELETE ON websites
  FOR EACH STATEMENT EXECUTE FUNCTION update_stats_count();

-- ============================================================
-- 4. FUNCTION — Optimized random active website
-- ============================================================
CREATE OR REPLACE FUNCTION get_random_active_website()
RETURNS TABLE(id BIGINT, url TEXT, domain TEXT) AS $$
BEGIN
  RETURN QUERY
    SELECT w.id, w.url, w.domain
    FROM websites w
    WHERE w.is_active = true
    ORDER BY random()
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- 5. ROW LEVEL SECURITY
-- ============================================================
ALTER TABLE websites ENABLE ROW LEVEL SECURITY;
ALTER TABLE stats ENABLE ROW LEVEL SECURITY;

-- Public read access for frontend (publishable key)
CREATE POLICY "Allow public read on websites"
  ON websites FOR SELECT
  USING (true);

CREATE POLICY "Allow public read on stats"
  ON stats FOR SELECT
  USING (true);

-- Allow inserts/updates from authenticated or service role
CREATE POLICY "Allow service write on websites"
  ON websites FOR ALL
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Allow service write on stats"
  ON stats FOR ALL
  USING (true)
  WITH CHECK (true);

-- ============================================================
-- 6. ENABLE REALTIME on stats table
-- ============================================================
ALTER PUBLICATION supabase_realtime ADD TABLE stats;
