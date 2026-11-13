# Deploying Klipr on Vercel

This repository is a Vercel Services monorepo. `vercel.json` deploys the Next.js app at `/` and routes the FastAPI request API through `/api`.

The repository's Dockerfiles are intentionally excluded from the Vercel upload via `.vercelignore`. They remain available for local Docker Compose use and for the persistent Celery worker host; excluding them prevents Vercel from classifying either HTTP service as a generic Container instead of its explicitly configured framework.

The API uses `backend/requirements.txt`, which deliberately excludes `faster-whisper`, NumPy, and Streamlink so the Vercel Function stays below its bundle-size limit. The persistent worker installs `backend/requirements.worker.txt`, which includes those media dependencies.

## Import settings

1. In the import screen shown, keep **Application Preset: Services** and import the multi-service project.
2. Add `NEXT_PUBLIC_API_URL=/api` to Vercel's Production, Preview, and Development environment variables.
3. Add the production values for `DATABASE_URL`, `REDIS_URL`, and the R2 variables from `.env.example` to the **api** service.
4. Add `KLIPR_ACCESS_PASSWORD` and a long random `KLIPR_SESSION_SECRET` to the **api** service. These are server-only values; do not use `NEXT_PUBLIC_` prefixes or commit them. Set `KLIPR_SECURE_COOKIES=true` for Vercel.

## Required worker deployment

Do not deploy the `worker` Docker service to Vercel. Stream recording, FFmpeg, and faster-whisper are long-running queue workloads. Run the `worker` service from `docker-compose.yml` on a persistent container host, such as Railway, Render, Fly.io, ECS, or a VPS, with the same `DATABASE_URL`, `REDIS_URL`, and R2 variables as the API.

The public Vercel API safely enqueues jobs into Redis; the persistent worker consumes them. Vercel Functions are time-limited, so they cannot reliably hold a live stream capture open indefinitely.
