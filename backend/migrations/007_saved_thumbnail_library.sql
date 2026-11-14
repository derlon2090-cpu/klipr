CREATE TABLE IF NOT EXISTS saved_thumbnails (
    id UUID PRIMARY KEY,
    kind VARCHAR(16) NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT saved_thumbnails_kind_check CHECK (kind IN ('vod', 'short'))
);
CREATE INDEX IF NOT EXISTS ix_saved_thumbnails_kind ON saved_thumbnails(kind);
