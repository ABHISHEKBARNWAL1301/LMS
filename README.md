# EvolveU Backend

Backend services for [EvolveU](https://evolveu.in/), an online learning platform for Spoken English, Accounting and Taxation.

```text
backend/               REST API (FastAPI, PostgreSQL, SQLAlchemy, Alembic)
transcoding-service/   Video transcoding to multi-bitrate HLS (FFmpeg, Cloudflare R2)
```

## How the pieces fit

```text
Admin uploads a lesson video ─► API stores the original in R2
                              └► POST /transcode ─► transcoding service
                                                    ├─ FFmpeg: 480p, 720p, 1080p HLS renditions
                                                    ├─ uploads playlists + segments to R2
                                                    └─ POST /transcoding/webhook ─► API marks the lesson ready
Student opens a lesson ─► API returns the HLS master playlist URL ─► adaptive playback in the browser
```

## API (`backend/`)

- **Auth:** JWT access tokens, password login, phone OTP login (MSG91), password reset by email
- **Access control:** student, instructor and admin roles; enrollment checks before paid content
- **Catalog:** courses, lessons (video and quiz), course overviews, packages, FAQs, ratings, instructors
- **Payments:** Razorpay orders, signature verification, coupons
- **Content:** blog, gallery, contact form
- **Schema changes:** Alembic migrations in `backend/migrations/`

### Run locally

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the values
docker compose up -d db       # local PostgreSQL
alembic upgrade head
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

## Transcoding service (`transcoding-service/`)

```bash
cd transcoding-service
cp .env.example .env          # then fill in the values
docker build -t evolveu-transcoder .
docker run --env-file .env -p 8001:8000 evolveu-transcoder
```

Endpoints: `POST /transcode` starts a job in the background; `GET /health`.

## Configuration

Each service reads its settings from a `.env` file; `.env.example` lists every variable. Never commit a real `.env`.
