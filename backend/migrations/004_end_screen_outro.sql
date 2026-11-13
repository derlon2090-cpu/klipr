ALTER TABLE streams ADD COLUMN IF NOT EXISTS archive_channel_name VARCHAR(120);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS outro_duration_seconds INTEGER NOT NULL DEFAULT 15;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS left_vod_id UUID;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS right_vod_id UUID;
ALTER TABLE streams ADD CONSTRAINT streams_outro_duration_check CHECK (outro_duration_seconds BETWEEN 10 AND 20);
