ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_thumbnail_key TEXT;
ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS default_short_thumbnail_key TEXT;
ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS use_default_thumbnail BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS short_thumbnail_key TEXT;
