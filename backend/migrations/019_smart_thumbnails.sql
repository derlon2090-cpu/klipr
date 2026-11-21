CREATE TABLE IF NOT EXISTS smart_thumbnails (
  id UUID PRIMARY KEY,
  vod_id UUID NOT NULL REFERENCES vods(id) ON DELETE CASCADE,
  status VARCHAR(16) NOT NULL DEFAULT 'queued',
  progress DOUBLE PRECISION NOT NULL DEFAULT 0,
  platform VARCHAR(24) NOT NULL DEFAULT 'youtube',
  frame_style VARCHAR(24) NOT NULL DEFAULT 'bold',
  timestamp_seconds DOUBLE PRECISION,
  headline VARCHAR(160),
  context TEXT,
  output_path TEXT,
  error_message TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_smart_thumbnails_vod_id ON smart_thumbnails(vod_id);


