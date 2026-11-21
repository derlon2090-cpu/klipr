-- VODs routinely exceed PostgreSQL INTEGER's 2 GiB-ish byte ceiling.
ALTER TABLE vods ALTER COLUMN file_size TYPE BIGINT;
