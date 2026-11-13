# Deploying Klipr on Vercel

This repository is a Vercel Services monorepo. `vercel.json` deploys the Next.js app at `/` and routes the FastAPI request API through `/api`.

## Import settings

1. In the import screen shown, keep **Application Preset: Services** and import the multi-service project.
2. Add `NEXT_PUBLIC_API_URL=/api` to Vercel's Production, Preview, and Development environment variables.
3. Add the production values for `DATABASE_URL`, `REDIS_URL`, and the R2 variables from `.env.example` to the **api** service.

## Required worker deployment

Do not deploy the `worker` Docker service to Vercel. Stream recording, FFmpeg, and faster-whisper are long-running queue workloads. Run the `worker` service from `docker-compose.yml` on a persistent container host, such as Railway, Render, Fly.io, ECS, or a VPS, with the same `DATABASE_URL`, `REDIS_URL`, and R2 variables as the API.

The public Vercel API safely enqueues jobs into Redis; the persistent worker consumes them. Vercel Functions are time-limited, so they cannot reliably hold a live stream capture open indefinitely.
