-- Encrypted values only: plaintext cookies and tokens never reach this schema.
CREATE TABLE IF NOT EXISTS session_credentials (
  platform VARCHAR(16) PRIMARY KEY CHECK (platform IN ('kick', 'twitch')),
  session_encrypted TEXT,
  status VARCHAR(16) NOT NULL DEFAULT 'unset'
    CHECK (status IN ('active', 'expiring_soon', 'expired', 'unset')),
  updated_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ
);

ALTER TABLE archive_branding
  ADD COLUMN IF NOT EXISTS auto_trim_ads BOOLEAN NOT NULL DEFAULT FALSE;

-- Session expiry is a first-class bell alert.
ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notification_status_check;
ALTER TABLE notifications ADD CONSTRAINT notification_status_check
  CHECK (status IN ('pending_auto_record','auto_started','cancelled','manual_taken_over','session_expired'));
