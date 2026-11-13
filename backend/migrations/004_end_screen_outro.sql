ALTER TABLE streams ADD COLUMN IF NOT EXISTS archive_channel_name VARCHAR(120);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS outro_duration_seconds INTEGER NOT NULL DEFAULT 15;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS left_vod_id UUID;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS right_vod_id UUID;
ALTER TABLE streams ADD CONSTRAINT streams_outro_duration_check CHECK (outro_duration_seconds BETWEEN 10 AND 20);
CREATE TABLE IF NOT EXISTS archive_branding (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), enable_end_screen BOOLEAN NOT NULL DEFAULT TRUE,
  outro_duration_seconds INTEGER NOT NULL DEFAULT 15 CHECK (outro_duration_seconds BETWEEN 10 AND 20),
  archive_channel_name VARCHAR(120), archive_tagline VARCHAR(240), archive_logo_key TEXT,
  default_left_vod_id UUID, default_right_vod_id UUID
);
