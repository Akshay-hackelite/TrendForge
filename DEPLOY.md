# TrendForge — Deploy guide

Stack: **Vercel** (frontend) + **Render** (FastAPI) + **MongoDB Atlas** (data) + optional **GCP Cloud Storage** (uploads) + **GitHub** (auto-deploy).

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

## 2. Google Cloud Storage (your bucket)

Required on **Render** for Instagram images, PDFs, and other uploads. Local dev can skip GCS (falls back to disk; ephemeral on Render).

### 2a. Create GCP project + bucket

1. [console.cloud.google.com](https://console.cloud.google.com/) → **New project** (e.g. `trendforge`).
2. **APIs & Services → Enable APIs** → enable **Cloud Storage API**.
3. **Cloud Storage → Buckets → Create**
   - Name: globally unique, e.g. `trendforge-media-akshay`
   - Location: region near you (e.g. `asia-south1`)
   - Access control: **Uniform**
   - **Create**
4. **Public read for uploaded files** (Instagram/YouTube must fetch URLs):
   - Bucket → **Permissions** → **Grant access**
   - Principal: `allUsers`
   - Role: **Storage Object Viewer**
   - Or use a bucket policy that allows public read on object URLs the app returns (`https://storage.googleapis.com/BUCKET/...`).

### 2b. Service account + JSON key

1. **IAM & Admin → Service Accounts → Create**
   - Name: `trendforge-storage`
2. **Keys → Add key → JSON** → download the file.
3. **Bucket → Permissions** → grant that service account **Storage Object Admin** on the bucket.

### 2c. Put in `.env` / Render

**Option A — inline JSON (Render-friendly):**

Minify the JSON to one line:

```bash
python3 -c "import json; print(json.dumps(json.load(open('path/to/key.json'))))"
```

Set:

```env
GCS_BUCKET_NAME=trendforge-media-akshay
GCS_KEY_JSON={"type":"service_account","project_id":"...",...}
```

**Option B — local file:** set `GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json` and leave `GCS_KEY_JSON` empty (local only).

### 2d. Rotate away from office bucket

If `.env` still has an old bucket (e.g. `gravity-storage-0` / project `supdoc-*`):

1. Create **your** bucket + service account (above).
2. Update `GCS_BUCKET_NAME` and `GCS_KEY_JSON` in `.env` and Render.
3. In the **office** GCP project → **IAM → Service Accounts** → delete or rotate the old key you were using (so that credential stops working).
4. Redeploy Render.

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
| `GCS_BUCKET_NAME` | Your bucket name |
| `GCS_KEY_JSON` | Service account JSON (one line) |

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
| **GCS** | Your bucket + service account; delete office SA key |
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
- [ ] Upload test (social image) hits **your** GCS bucket
- [ ] Atlas shows data under **your** database name
- [ ] Cron test:
  ```bash
  curl -X POST "https://YOUR-SERVICE.onrender.com/cron/social.generate-festivals" \
    -H "X-Cron-Secret: YOUR_CRON_SECRET"
  ```
- [ ] Office GCS key rotated/deleted in old GCP project

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
| Uploads | GCS optional (disk fallback) | GCS required |

Put Atlas URI and secrets in repo-root `.env` and restart the API.
