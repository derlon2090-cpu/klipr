CREATE TABLE IF NOT EXISTS creator_suggestions (
    id UUID PRIMARY KEY,
    creator_name VARCHAR(120) NOT NULL,
    platform VARCHAR(16) NOT NULL,
    channel_url TEXT,
    status VARCHAR(16) NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT creator_suggestions_platform_check CHECK (platform IN ('twitch', 'kick')),
    CONSTRAINT creator_suggestions_status_check CHECK (status IN ('new', 'reviewed'))
);

CREATE INDEX IF NOT EXISTS ix_creator_suggestions_status_created
    ON creator_suggestions(status, created_at DESC);
