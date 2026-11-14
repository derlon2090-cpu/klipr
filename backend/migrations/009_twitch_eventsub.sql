ALTER TABLE watchlist_subscriptions ADD COLUMN IF NOT EXISTS twitch_user_id VARCHAR(64);
ALTER TABLE watchlist_subscriptions ADD COLUMN IF NOT EXISTS eventsub_subscription_id VARCHAR(255);
CREATE INDEX IF NOT EXISTS ix_watchlist_twitch_user_id ON watchlist_subscriptions(twitch_user_id);
