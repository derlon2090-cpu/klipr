CREATE TABLE IF NOT EXISTS studio_renders (
  id UUID PRIMARY KEY,
  vod_id UUID NOT NULL REFERENCES vods(id) ON DELETE CASCADE,
  status VARCHAR(16) NOT NULL DEFAULT 'queued',
  progress DOUBLE PRECISION NOT NULL DEFAULT 0,
  thumbnail_path TEXT,
  intro_path TEXT,
  outro_path TEXT,
  output_path TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT studio_renders_status_check CHECK (status IN ('queued', 'processing', 'ready', 'failed'))
);
CREATE INDEX IF NOT EXISTS ix_studio_renders_vod_id ON studio_renders(vod_id);
