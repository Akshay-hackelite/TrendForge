# TrendForge — Deploy guide

Stack: **Vercel** (frontend) + **Render** (FastAPI) + **MongoDB Atlas** (data) + **Supabase Storage** (uploads, default) + **GitHub** (auto-deploy). GCS remains in code for a later paid switch.

Repo: [Akshay-hackelite/TrendForge](https://github.com/Akshay-hackelite/TrendForge)

---

## 0. Push to GitHub

```bash
git add -A
git status   # confirm .env and db.json are NOT listed
git commit -m "Your message"
git push origin main
```

Never commit `.env` or `backend/db.json`.

---

## 1. MongoDB Atlas (your cluster)

Use **your own** Atlas account — not an office/shared cluster.

1. [mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas) → create **Free M0** cluster.
2. **Database Access** → add user + strong password.
3. **Network Access** → **Allow Access from Anywhere** (`0.0.0.0/0`) for Render free tier.
4. **Connect** → Drivers → copy URI:
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
5. Set on Render:
   - `MONGODB_URI` = that URI
   - `MONGODB_DB_NAME` = e.g. `trendforge` (your choice)

**Verify it's yours:** Atlas project name and billing account are under your Google/email login. If the URI still points at an office cluster, create a new cluster and update `MONGODB_URI`.

Collections created on first use: `users`, `clients`, `channels`, `videos`, `topics`, `content_plans`, …

---

## 2. File storage (Supabase default, GCS switcher)

Uploads (Instagram images, thumbnails, videos, PDFs) go through `STORAGE_BACKEND`:

| `STORAGE_BACKEND` | Where new files go |
|-------------------|--------------------|
| `supabase` (default) | Supabase Storage — no credit card, public URLs |
| `gcs` | Google Cloud Storage — keep for later when you pay |

Mongo still stores a public HTTPS URL. Instagram/Facebook fetch that URL. Local disk is used only if cloud upload fails (fine locally; **not** enough on Render).

**Free-tier limit:** each file must be **50 MB or smaller** (1 GB total). Images, PDFs, and thumbnails are fine; large videos fail until you switch to `gcs` or upgrade Supabase.

The Postgres **Data API** can stay off. Storage does not need it.

### 2a. Supabase Storage (what to use now)

1. [supabase.com/dashboard](https://supabase.com/dashboard) → **New project** (any region; Mumbai is fine). No credit card on the free plan.
2. **Storage → New bucket**
   - Name: `media` (or any name — must match `SUPABASE_BUCKET`)
   - **Public bucket:** ON (Instagram must fetch the URL)
   - Create
3. **Project Settings → API**
   - Copy **Project URL** → `SUPABASE_URL`
   - Copy **service_role** (secret) → `SUPABASE_SERVICE_ROLE_KEY`
   - Never use the **anon** key on the backend

```env
STORAGE_BACKEND=supabase
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_BUCKET=media
```

Public file URLs look like:

`https://YOUR_PROJECT.supabase.co/storage/v1/object/public/media/generated_images/foo.png`

Folders in the bucket match the app: `generated_images`, `uploads`, `uploaded_videos`, `social_post_videos`, `weekly_tracker`, `thumbnails`, `reports`.

### 2b. Switch back to GCS later (paid)

GCS code stays in the repo. No caller rewrite needed.

```env
STORAGE_BACKEND=gcs
GCS_BUCKET_NAME=your-paid-bucket
GCS_KEY_JSON={"type":"service_account",...}
```

Restart the API. New uploads go to GCS. Old Supabase URLs in Mongo keep working. Deletes follow the URL host.

Office `GCS_*` values can stay in `.env` unused while `STORAGE_BACKEND=supabase`.

---

## 3. Render — backend API

1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** (or Web Service).
   - Repo: `Akshay-hackelite/TrendForge`
   - **Root Directory:** `backend`
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Set environment variables (see **Full env checklist** below).
3. Deploy → note URL: `https://YOUR-SERVICE.onrender.com`
4. Smoke test: `GET https://YOUR-SERVICE.onrender.com/health` → `{"status":"ok"}`

**Free tier:** sleeps after ~15 min idle; first request may take 30–60s.

---

## 4. Vercel — frontend

1. [vercel.com](https://vercel.com) → import `Akshay-hackelite/TrendForge`.
2. **Root Directory:** `frontend`
3. **Framework:** Vite
4. Environment:
   - `VITE_API_URL` = `https://YOUR-SERVICE.onrender.com` (no trailing slash)
5. Deploy → note `https://your-app.vercel.app`
6. Update Render:
   - `FRONTEND_URL=https://your-app.vercel.app`
   - `CORS_ORIGINS=https://your-app.vercel.app`
   - `BASE_URL=https://YOUR-SERVICE.onrender.com`
   - Redeploy backend.

---

## 5. Google OAuth (YouTube connect)

Use **your** OAuth client in the same (or linked) GCP project.

1. **APIs & Services → Credentials → OAuth 2.0 Client**
2. **Authorized redirect URIs:**
   - `https://YOUR-SERVICE.onrender.com/google.callback`
   - `http://localhost:8000/google.callback` (local dev)
3. Set on Render:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `GOOGLE_REDIRECT_URI=https://YOUR-SERVICE.onrender.com/google.callback`

---

## 6. Cron jobs (festive drafts + scheduled publish)

Endpoints (both require header `X-Cron-Secret: <CRON_SECRET>`):

| Job | Endpoint | Suggested time (IST) |
|-----|----------|----------------------|
| Generate festival drafts | `POST /cron/social.generate-festivals` | ~01:00 daily |
| Publish scheduled posts | `POST /cron/social.publish-scheduled` | ~09:00 daily |

Generate a secret:

```bash
openssl rand -hex 32
```

Set `CRON_SECRET` on Render to that value. Use the **same** value in your scheduler.

### Scheduler options (any HTTP cron)

**GCP Cloud Scheduler** (example):

```bash
gcloud scheduler jobs create http trendforge-festivals \
  --schedule="0 1 * * *" \
  --time-zone="Asia/Kolkata" \
  --uri="https://YOUR-SERVICE.onrender.com/cron/social.generate-festivals" \
  --http-method=POST \
  --headers="X-Cron-Secret=YOUR_CRON_SECRET"
```

**cron-job.org** (free): create two jobs with POST + custom header `X-Cron-Secret`.

**GitHub Actions** `schedule:` — curl your Render URL with the header.

Crons always target your **deployed** API URL, not localhost.

---

## 7. Full env checklist

### Render (backend) — required

| Variable | Example / notes |
|----------|-----------------|
| `MONGODB_URI` | Your Atlas URI |
| `MONGODB_DB_NAME` | `trendforge` |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `GOOGLE_CLIENT_ID` | Your OAuth client |
| `GOOGLE_CLIENT_SECRET` | Your OAuth secret |
| `GOOGLE_REDIRECT_URI` | `https://API.onrender.com/google.callback` |
| `FRONTEND_URL` | `https://app.vercel.app` |
| `CORS_ORIGINS` | `https://app.vercel.app` |
| `BASE_URL` | `https://API.onrender.com` |
| `OPENAI_API_KEY` | Your key |
| `CRON_SECRET` | Random string (see §6) |
| `ADMIN_PASSWORD` | Random string for `/admin` dashboard |
| `STORAGE_BACKEND` | `supabase` (now) or `gcs` (later) |
| `SUPABASE_URL` | `https://YOUR_PROJECT.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → `service_role` |
| `SUPABASE_BUCKET` | Public bucket name, e.g. `media` |

### Render — recommended

| Variable | Default in repo |
|----------|-----------------|
| `SERPAPI_API_KEY` | For Google Trends scoring |
| `OPENAI_MODEL` | `gpt-5.6-luna` |
| `OPENAI_REASONING_EFFORT` | `low` |
| `OPENAI_TTS_MODEL` | `gpt-4o-mini-tts` |
| `TRENDS_GEO` | `IN` |

### Render — production hygiene

| Variable | Production value |
|----------|------------------|
| `SEED_DEMO_USERNAME` | **Leave empty** (do not seed office demo user) |
| `SEED_DEMO_PASSWORD` | **Leave empty** |

Create your login via **Register** on the app, or `/admin` after setting `ADMIN_PASSWORD`.

### Render — social (when using Instagram/Facebook)

| Variable | Notes |
|----------|-------|
| `INSTAGRAM_REDIRECT_URI` | `https://API.onrender.com/social.instagram.callback` |
| `FACEBOOK_REDIRECT_URI` | `https://API.onrender.com/social.facebook.callback` |

Per-client Instagram app id/secret are stored in the DB (Settings), not env.

### Vercel (frontend)

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://YOUR-SERVICE.onrender.com` |

### Local `.env` only (optional)

| Variable | Notes |
|----------|-------|
| `SEED_DEMO_USERNAME` | e.g. `devuser` for local first-boot login |
| `SEED_DEMO_PASSWORD` | matching password |

---

## 8. Make everything yours — ownership checklist

| Item | What to change |
|------|----------------|
| **GitHub** | `Akshay-hackelite/TrendForge` ✅ |
| **MongoDB** | Your Atlas URI + DB name; not office cluster |
| **File storage** | Supabase Storage (`STORAGE_BACKEND=supabase`); GCS code kept for later |
| **Google OAuth** | Your client id/secret + production redirect URI |
| **OpenAI / SerpApi** | Your API keys in Render + `.env` |
| **CRON_SECRET** | New random string (was hardcoded `gravity-cron-secret`) |
| **ADMIN_PASSWORD** | New random string (was hardcoded `gravityAdmin!2026`) |
| **Demo user** | Leave `SEED_DEMO_USERNAME` empty on Render; register your own user |
| **Existing RipplicaTeam in DB** | `/admin` → reset password or delete user |
| **Render / Vercel** | Your accounts, not office |
| **Instagram ngrok URIs** | Replace with production Render URLs when deployed |

### Demo password in production

If the API already seeded `RipplicaTeam`:

1. Set `ADMIN_PASSWORD` on Render.
2. Open `https://your-app.vercel.app/admin`.
3. Reset password for `RipplicaTeam` **or** delete that user and register a new account.

If deploying fresh with empty `SEED_DEMO_USERNAME`, no demo user is created.

---

## 9. After deploy checklist

- [ ] `GET /health` returns ok
- [ ] Login with **your** account (not shared demo creds)
- [ ] `/admin` works with your `ADMIN_PASSWORD`
- [ ] YouTube OAuth connect works
- [ ] Upload test (social image) URL is `*.supabase.co/storage/v1/object/public/...` (not office GCS)
- [ ] Atlas shows data under **your** database name
- [ ] Cron test:
  ```bash
  curl -X POST "https://YOUR-SERVICE.onrender.com/cron/social.generate-festivals" \
    -H "X-Cron-Secret: YOUR_CRON_SECRET"
  ```
- [ ] Office GCS is unused (`STORAGE_BACKEND=supabase`); rotate office SA key when ready

---

## 10. CI/CD

| Host | Trigger |
|------|---------|
| **Vercel** | Push to `main` → frontend rebuild |
| **Render** | Push to `main` → API rebuild (enable Auto-Deploy) |

---

## Local vs production

| | Local | Production |
|--|--------|------------|
| Frontend | `make start-frontend` → :5173 | Vercel |
| Backend | `make start-backend` → :8000 | Render |
| Data | MongoDB Atlas (`MONGODB_URI`) | MongoDB Atlas |
| Uploads | Supabase (`STORAGE_BACKEND=supabase`) or local disk fallback | Supabase required on Render |

Put Atlas URI and secrets in repo-root `.env` and restart the API.
