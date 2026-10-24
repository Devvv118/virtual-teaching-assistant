# Virtual Teaching Assistant — terminal frontend

React + Vite + Tailwind 4, styled after the portfolio's *Terminal* project layout.
It talks to `backend/main.py` only.

## Run

```bash
# 1. backend (terminal 1)
cd backend
pip install -r requirements.txt
cp .env.example .env        # fill in AIPIPE_TOKEN and DATABASE_URL
python main.py              # serves on http://localhost:8000

# 2. frontend (terminal 2)
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

Point the UI at a different backend with `VITE_API_URL` (see `.env.example`).

## What it does

1. On load it polls `GET /` until the backend answers (handles Render cold starts), and
   gives up after 60 seconds.
2. You enter a **question** and, optionally, a **link** (a `tds.s-anand.net/#/…` page or a
   Discourse thread — same rules as the backend).
3. `POST /api/stream` streams one JSON line per pipeline step (budget check, embedding,
   vector search, neighbouring posts, LLM call ...), shown live like terminal output.
4. The answer is rendered as markdown, followed by the source chunks.

The original `POST /api` endpoint still works and returns `{ answer, links }`.
