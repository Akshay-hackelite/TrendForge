# Deploy guide (free stack)

Stack: **Vercel** (frontend) + **Render** (FastAPI) + **MongoDB Atlas** (data) + **GitHub** (CI/CD via auto-deploy).

Set `MONGODB_URI` (Atlas). The API uses flat collections: `users`, `clients`, `channels`, `videos`, `topics`, `content_plans`.

---

## 0. Push this repo to GitHub

If you have not already:

```bash
git add -A
git status   # confirm .env and db.json are NOT listed
git commit -m "Prepare deploy: Mongo backing + Render/Vercel config"
git push -u origin main
```

Never commit `.env` or `backend/db.json` (they hold secrets / OAuth tokens).

---

## 1. MongoDB Atlas (free)

1. Go to [https://www.mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas) → sign up / log in.
2. Create a **Free (M0)** cluster (any cloud region close to you).
3. **Database Access** → Add user → username + password (save the password).
4. **Network Access** → Add IP Address → **Allow Access from Anywhere** (`0.0.0.0/0`) for a simple free deploy (Render’s IPs change).
5. **Database** → **Connect** → **Drivers** → copy the URI, e.g.  
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
6. Keep this URI for Render (`MONGODB_URI`).

After the API first starts, Atlas shows collections `users`, `clients`, `channels`, `videos`, `topics`, `content_plans`.

---

## 2. Render — backend API (free)

1. Go to [https://dashboard.render.com](https://dashboard.render.com) → sign up with **GitHub**.
2. **New** → **Blueprint** → select repo `test-gravity` (or **Web Service** and point at the same repo).
   - If using Web Service manually:
     - **Root Directory:** `backend`
     - **Runtime:** Python 3
     - **Build Command:** `pip install -r requirements.txt`
     - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
3. After create, open the service → **Environment** and set:

| Key | Value |
|-----|--------|
| `MONGODB_URI` | Atlas URI from step 1 |
| `MONGODB_DB_NAME` | `youtube_analytics` |
| `SECRET_KEY` | long random string |
| `GOOGLE_CLIENT_ID` | from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | from Google Cloud Console |
| `GOOGLE_REDIRECT_URI` | `https://YOUR-SERVICE.onrender.com/google.callback` |
| `FRONTEND_URL` | `https://YOUR-APP.vercel.app` *(fill after step 3, then update)* |
| `CORS_ORIGINS` | `https://YOUR-APP.vercel.app` |
| `OPENAI_API_KEY` | your key |
| `SERPAPI_API_KEY` | if you use Google Trends scoring |

4. Deploy. Note the URL: `https://youtube-analytics-api-xxxx.onrender.com`.
5. Smoke test: open `https://YOUR-SERVICE.onrender.com/health` → `{"status":"ok"}`.

**Free tier note:** the service sleeps after ~15 min idle; first request can take 30–60s.

---

## 3. Vercel — frontend (free)

1. Go to [https://vercel.com](https://vercel.com) → sign up with **GitHub**.
2. **Add New Project** → import `test-gravity`.
3. Configure:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite
   - **Build Command:** `npm run build` (default)
   - **Output Directory:** `dist` (default)
4. **Environment Variables:**
   - `VITE_API_URL` = `https://YOUR-SERVICE.onrender.com` (no trailing slash)
5. Deploy. Note the URL: `https://your-app.vercel.app`.
6. Go back to **Render** and set:
   - `FRONTEND_URL=https://your-app.vercel.app`
   - `CORS_ORIGINS=https://your-app.vercel.app`
   Then **Manual Deploy** → clear build cache / redeploy so CORS picks up.

---

## 4. Google OAuth (required for YouTube connect)

1. [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.
2. Edit your OAuth 2.0 Client.
3. **Authorized redirect URIs** → add:  
   `https://YOUR-SERVICE.onrender.com/google.callback`
4. Keep the local URI too if you still develop locally:  
   `http://localhost:8000/google.callback`

---

## 5. CI/CD (already wired)

You do not need GitHub Actions for deploy:

| Host | Trigger |
|------|---------|
| **Vercel** | Push to `main` → rebuild frontend. PRs get preview URLs. |
| **Render** | Push to `main` → rebuild API (enable Auto-Deploy in service settings). |

Optional later: a GitHub Action that only runs `npm run lint` / tests on PRs.

---

## 6. After deploy checklist

- [ ] `GET /health` on Render returns ok  
- [ ] Open Vercel URL → login (`RipplicaTeam` / `jaiHanuman` is seeded on first boot)  
- [ ] Change the demo password in production (or create a new user via admin)  
- [ ] Connect a YouTube channel (OAuth redirect works)  
- [ ] Atlas shows collections under `youtube_analytics` (`users`, `clients`, `channels`, `videos`, …)  

---

## Local vs production

| | Local | Production |
|--|--------|------------|
| Frontend | `npm run dev` → :5173 | Vercel |
| Backend | `make start-backend` → :8000 | Render |
| Data | MongoDB Atlas (`MONGODB_URI`) | MongoDB Atlas (`MONGODB_URI`) |

Put your Atlas URI in `.env` as `MONGODB_URI=...` and restart the API.

### Collections

| Collection | Key (`_id`) | Links |
|------------|-------------|--------|
| `users` | username | `active_client_id`, `active_channel_id` |
| `clients` | client uuid | `username` |
| `channels` | YouTube channel id | `client_id`, `username` |
| `videos` | YouTube video id | `channel_id`, `client_id` |
| `topics` | topic uuid | `client_id` |
| `content_plans` | client uuid | coverage + suggestions |
