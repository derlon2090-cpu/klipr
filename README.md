# Klipr.cloud MVP foundation

1. Copy `.env.example` to `.env` and provide a secure Postgres password and Cloudflare R2 credentials.
2. Start with `docker compose up --build`.
3. API health is available at `http://localhost:8000/health`; the dashboard shell is at `http://localhost:3000`.

The worker pipes `streamlink` into FFmpeg's copy-mode segment muxer, uploads completed TS chunks to R2, reconnects with bounded exponential backoff, and concatenates a final master MP4. Finalization automatically queues the highlight worker. It downloads the VOD, extracts a 16 kHz WAV, combines Whisper word timestamps with 5-second RMS audio energy, renders the three best non-overlapping 45-second clips as captioned 1080x1920 MP4s, uploads them to R2, and removes local processing artifacts.

For CPU development, retain `WHISPER_DEVICE=cpu` and `WHISPER_COMPUTE_TYPE=int8`. For a CUDA worker, set `WHISPER_DEVICE=cuda` and `WHISPER_COMPUTE_TYPE=float16`. Re-run a completed VOD with `POST /streams/{stream_id}/process`; retrieve clip URLs from `GET /streams/{stream_id}`. Presigned URLs expire after `R2_PRESIGNED_URL_TTL_SECONDS`.

Use Alembic instead of startup schema creation, authenticate API routes, and validate webhook signatures before a production deployment.

## Direct Twitch/Kick recording

`POST /streams/record` accepts only a live Twitch or Kick URL. It creates a Redis `active_stream:{url}` lock before dispatching the recording worker, so duplicate submissions are rejected without any scheduler or platform polling. `POST /streams/{id}/stop` requests a cooperative stop; the worker stitches the recorded chunks and queues AI clipping. For an existing database, apply [001_direct_ingestion.sql](backend/migrations/001_direct_ingestion.sql) once before deployment.
