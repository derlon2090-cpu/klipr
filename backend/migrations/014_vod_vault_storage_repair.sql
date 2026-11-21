-- Repairs deployments that recorded 009_vod_object_storage.sql before its
-- columns were committed.  Every statement is idempotent and non-destructive.
ALTER TABLE vods ADD COLUMN IF NOT EXISTS storage_key TEXT;
ALTER TABLE vods ADD COLUMN IF NOT EXISTS thumbnail_key TEXT;
