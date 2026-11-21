ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_logo_key TEXT;
ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_creator_name VARCHAR(120);
ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS overlay_position VARCHAR(24) NOT NULL DEFAULT 'top-right';
ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_logo_key TEXT;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_creator_name VARCHAR(120);
ALTER TABLE streams ADD COLUMN IF NOT EXISTS overlay_position VARCHAR(24) NOT NULL DEFAULT 'top-right';
