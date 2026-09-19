# YouTube Analytics

Split stack: React frontend (`app.xyz`) + FastAPI backend (`api.xyz`).

## Structure

```
backend/          # FastAPI API (port 8000)
frontend/         # React + Vite (port 5173)
Makefile          # make start-backend / make start-frontend
```

## Quick start

```bash
# One-time
make install-backend
make install-frontend

# Copy secrets (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET required)
cp .env.example .env   # or edit existing .env

# Terminal 1 — API at http://localhost:8000
make start-backend

# Terminal 2 — UI at http://localhost:5173
make start-frontend
```

Demo login: `RipplicaTeam` / `jaiHanuman`

## API (POST-only, dotted names)

All app endpoints are **POST**. Params go in the JSON body (login uses form-urlencoded).

| Endpoint | Body |
|----------|------|
| `POST /auth.register` | `{ username, password }` |
| `POST /auth.login` | form: `username`, `password` |
| `POST /auth.me` | — |
| `POST /client.list` | — |
| `POST /client.create` | `{ name }` |
| `POST /client.select` | `{ client_id }` |
| `POST /client.sync-channels` | `{ client_id?, channel_id? }` |
| `POST /client.delete` | `{ client_id }` |
| `POST /channel.list` | `{ client_id? }` |
| `POST /channel.get` | `{ channel_id?, client_id? }` |
| `POST /channel.select` | `{ channel_id, client_id? }` |
| `POST /channel.disconnect` | `{ channel_id, client_id }` |
| `POST /video.list` | `{ client_id?, channel_id? }` |
| `POST /video.get` | `{ video_id, client_id?, channel_id? }` |
| `POST /video.sync` | `{ client_id?, channel_id? }` |
| `POST /video.analytics` | `{ start_date, end_date, client_id?, channel_id?, ... }` |
| `POST /google.login` | `{ client_id }` |
| `GET /google.callback` | query: `code`, `state` *(Google redirect only)* |

Docs: http://localhost:8000/docs

## Deployment domains

| Service | Local | Production |
|---------|-------|------------|
| Frontend | `http://localhost:5173` | Vercel (`https://….vercel.app`) |
| Backend | `http://localhost:8000` | Render (`https://….onrender.com`) |
| Data | MongoDB Atlas (`MONGODB_URI`) | MongoDB Atlas flat collections (`MONGODB_URI`) |

**Step-by-step free deploy (GitHub + Atlas + Render + Vercel):** see [DEPLOY.md](./DEPLOY.md).

Set in `.env` / Vercel / Render:

- `FRONTEND_URL` / `CORS_ORIGINS` → your Vercel URL
- `GOOGLE_REDIRECT_URI` → `https://YOUR-API.onrender.com/google.callback`
- `VITE_API_URL` → your Render API URL
- `MONGODB_URI` → Atlas connection string (required in production)
