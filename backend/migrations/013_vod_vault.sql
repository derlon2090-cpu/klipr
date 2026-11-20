CREATE TABLE IF NOT EXISTS vods (
  id UUID PRIMARY KEY,
  source_url TEXT NOT NULL UNIQUE,
  platform VARCHAR(16) NOT NULL CHECK (platform IN ('kick', 'twitch')),
  quality VARCHAR(32) NOT NULL DEFAULT 'best',
  status VARCHAR(32) NOT NULL DEFAULT 'fetching_metadata'
    CHECK (status IN ('fetching_metadata', 'downloading', 'remuxing', 'ready', 'failed')),
  title VARCHAR(500),
  streamer_name VARCHAR(160),
  duration_seconds INTEGER,
  thumbnail_url TEXT,
  local_path TEXT,
  thumbnail_path TEXT,
  file_size BIGINT,
  progress DOUBLE PRECISION NOT NULL DEFAULT 0,
  download_speed VARCHAR(64),
  eta_seconds INTEGER,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_vods_status_created_at ON vods(status, created_at DESC);
