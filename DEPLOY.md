# Deployment Guide — Free, No Credit Card

## Recommended Stack (100% free, no CC ever)

| Layer | Service | Cost | CC Required |
|---|---|---|---|
| Database | Supabase PostgreSQL | Free forever (500MB) | No |
| Backend + Frontend | HuggingFace Spaces | Free (2vCPU, 16GB RAM) | No |
| OR: Frontend only | Vercel | Free (100GB bandwidth) | No |

---

## Option A: HuggingFace Spaces (all-in-one, simplest)

Everything — React frontend + FastAPI backend — runs in one Docker container.

### Step 1: Get Supabase PostgreSQL (free, no CC)

1. Go to **supabase.com** → Sign up with GitHub (no CC needed)
2. Create a new project → choose a region close to you
3. Wait ~2 min for setup
4. Go to **Settings → Database → Connection string → URI**
5. Copy the connection string — it looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.xxxxxxxxxxxx.supabase.co:5432/postgres
   ```
6. Save this — you'll need it in the next step

### Step 2: Deploy to HuggingFace Spaces

1. Go to **huggingface.co** → Sign up (free, no CC)
2. Click your profile → **New Space**
3. Settings:
   - **Space name**: `ppc-intel` (or anything)
   - **SDK**: `Docker`
   - **Visibility**: Private ← important, keeps your data secure
4. Click **Create Space**
5. In the Space, go to **Settings → Variables and secrets**
6. Add these secrets (click the lock icon — they're encrypted):
   ```
   ANTHROPIC_API_KEY = sk-ant-...your key...
   DATABASE_URL      = postgresql://postgres:...your supabase URL...
   ```
7. Go to **Files** tab → click **Upload files**
8. Upload all files from this project (or connect via Git — see below)

### Step 3: Connect via Git (easier for updates)

```bash
# Install HuggingFace CLI
pip install huggingface_hub

# Login
huggingface-cli login   # paste your HF token from Settings → Access Tokens

# Add HF as remote (replace YOUR_USERNAME and SPACE_NAME)
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/SPACE_NAME

# Push
git push hf main
```

The Space will auto-build and deploy. Build takes ~3-5 minutes.
Access your app at: `https://YOUR_USERNAME-SPACE_NAME.hf.space`

---

## Option B: Split Deployment (React on Vercel + API on HuggingFace)

Better if you want faster frontend updates independently.

### Frontend → Vercel (free, no CC)

1. **Build the frontend** to point to your HF Space URL:
   ```bash
   # In frontend/.env.production
   VITE_API_URL=https://YOUR_USERNAME-ppc-intel.hf.space
   ```
2. Update `frontend/src/pages/*.jsx` — change `const API = '/api'` to:
   ```js
   const API = import.meta.env.VITE_API_URL || '/api'
   ```
3. Go to **vercel.com** → Sign up with GitHub (no CC)
4. Import your GitHub repo → set **Root Directory** to `frontend`
5. Add environment variable: `VITE_API_URL` = your HF Space URL
6. Deploy → get `yourapp.vercel.app`

### Backend → HuggingFace Spaces (same as Option A above)
Add CORS header for your Vercel URL in `backend/main.py`:
```python
allow_origins=["https://yourapp.vercel.app", "http://localhost:5173"]
```

---

## Option C: Oracle Cloud Always Free (most powerful, needs CC once for verification)

4 ARM vCPUs, 24GB RAM, 200GB storage — never charged if you stay in free tier.
The CC is for identity verification only.

1. Sign up at **cloud.oracle.com** → Always Free account
2. Create an **Ampere A1 VM** (4 vCPU, 24GB RAM — all free)
3. SSH in, install Docker:
   ```bash
   curl -fsSL https://get.docker.com | sh
   ```
4. Clone your repo, create `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
5. Run:
   ```bash
   docker-compose up -d
   ```
6. App runs on port 8000. Use nginx as reverse proxy for HTTPS.

---

## Local Development

```bash
# Backend
cd backend
pip install -r ../requirements.txt fastapi uvicorn[standard] sse-starlette python-multipart anthropic apscheduler
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Backend: http://localhost:8000
Frontend: http://localhost:5173 (Vite proxies /api → :8000)

---

## Environment Variables Reference

| Variable | Where to set | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | HF Secrets / .env | Claude AI key |
| `DATABASE_URL` | HF Secrets / .env | PostgreSQL URL (Supabase). If empty, uses SQLite |
| `DB_PATH` | Optional | SQLite file path (default: /app/data/ppc_intel.db) |

---

## Supabase Free Tier Limits

- 500MB database
- Unlimited API requests
- **Never expires** (active project stays free)
- Pause after 1 week of inactivity (unpause is 1 click)
- To keep active: any DB query every 7 days (the daily scheduler handles this automatically)
