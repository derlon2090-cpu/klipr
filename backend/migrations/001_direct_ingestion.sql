-- Apply once to an existing Phase 1/2 PostgreSQL database before deploying Phase 3.
ALTER TABLE streams ALTER COLUMN channel_id DROP NOT NULL;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS platform VARCHAR(32) NOT NULL DEFAULT 'direct';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE streams DROP CONSTRAINT IF EXISTS streams_channel_id_fkey;
ALTER TABLE streams ADD CONSTRAINT streams_channel_id_fkey FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE SET NULL;
