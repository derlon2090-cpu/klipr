CREATE TABLE IF NOT EXISTS watchlist_subscriptions (
    id UUID PRIMARY KEY, platform VARCHAR(16) NOT NULL, channel_slug VARCHAR(100) NOT NULL,
    channel_url TEXT NOT NULL UNIQUE, display_name VARCHAR(120) NOT NULL, avatar_url TEXT,
    auto_record BOOLEAN NOT NULL DEFAULT TRUE, delay_seconds INTEGER NOT NULL DEFAULT 30,
    is_currently_live BOOLEAN NOT NULL DEFAULT FALSE, last_stream_id VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT watchlist_platform_check CHECK (platform IN ('twitch', 'kick')),
    CONSTRAINT watchlist_delay_check CHECK (delay_seconds BETWEEN 10 AND 300)
);
CREATE INDEX IF NOT EXISTS ix_watchlist_platform ON watchlist_subscriptions(platform);

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY, subscription_id UUID REFERENCES watchlist_subscriptions(id) ON DELETE SET NULL,
    title VARCHAR(200) NOT NULL, message TEXT NOT NULL, channel_url TEXT NOT NULL,
    status VARCHAR(32) NOT NULL, is_read BOOLEAN NOT NULL DEFAULT FALSE,
    scheduled_for TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT notification_status_check CHECK (status IN ('pending_auto_record','auto_started','cancelled','manual_taken_over'))
);
CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_subscription ON notifications(subscription_id);
