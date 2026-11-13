-- Apply after 001_direct_ingestion.sql on existing databases.
ALTER TABLE streams ADD COLUMN IF NOT EXISTS layout_mode VARCHAR(16) NOT NULL DEFAULT 'center';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS discord_webhook_url TEXT;
ALTER TABLE streams ADD CONSTRAINT streams_layout_mode_check CHECK (layout_mode IN ('center', 'split'));
