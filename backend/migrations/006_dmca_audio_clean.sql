-- Phase 8: default vocal isolation and a per-recording override.
ALTER TABLE archive_branding ADD COLUMN IF NOT EXISTS remove_music BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE streams ADD COLUMN IF NOT EXISTS remove_music BOOLEAN NOT NULL DEFAULT FALSE;
