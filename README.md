# compass-ai

Career coach for people who are currently employed and want to grow: perform better in their role, build skills, win a promotion, or move to a better job.

**Stack:** React + TypeScript (Vite) frontend, FastAPI backend, Supabase (sign-in + database), Llama 4 Maverick (Meta) through OpenRouter.

```
frontend/   React app (Vite, TypeScript). Signs users in with Supabase and calls the API.
compass/    Python: api.py (HTTP), jwt_auth.py, prompts, llm (OpenRouter), memory, documents, db, anonymise
database/   schema.sql (+ migrations/)
evals/      the 20 scenarios and the scoring runner
e2e/        a no-accounts fake stack and a real-browser check
tests/      pytest suite for the backend
```

How it fits together: the browser signs in with Supabase (emailed code), gets a JWT, and sends it with every call to `/api/...`. The API verifies the JWT against Supabase's JWKS, then talks to the database **as that user**, so Row Level Security keeps everyone's data apart. In production the FastAPI process also serves the built React app, so there is one thing to deploy.

## What's built

- **Chat:** streaming replies (server-sent events), markdown, thumbs up/down saved on each reply, past conversations in the sidebar (reopen and continue), starter prompts.
- **Memory:** "End session" has the model write a 5-line note; the last 5 notes go into the next conversation. If someone just closes the tab, the note is written the next time they sign in.
- **Profile** (role, industry, goals, pasted CV) and **Documents** (PDF, Word, text or Markdown; only the extracted text is kept; each can be switched on or off; the switched-on ones go into every conversation, newest first, up to 80,000 characters, and the coach cites them by name). Uploaded text is wrapped as data so instructions hidden in a document are not followed.
- **Consent screen** on first sign-in with a separate, optional, default-off tick box for using anonymised chats in training. Nothing is loaded or sent to the model until the user agrees. Bump `CONSENT_VERSION` in `compass/consent.py` to ask everyone again.
- **Privacy page:** change the training opt-in, or **delete my data** (one atomic database call removing chats, summaries, documents, profile and consent record, then sign out).
- **Cost guard:** per-user daily message limit (default 50).
- **Safety:** JWT verification (signature, issuer, audience, expiry; algorithm-confusion tokens refused), CSP and other security headers, the app refuses to start with a Supabase secret key, no message content in logs.
- **Evals** and an **anonymised export** for opted-in users (below).

Not yet (Week 3): onboarding testers, monitoring, and the Phase 1 baseline score.

## Setup

1. **Supabase:** create a project and run `database/schema.sql` in the SQL editor (safe to re-run; if you already ran the Week 1 version, run just `database/migrations/002_week2.sql`).
2. **Sign-in email:** users get an email with a sign-in link (and optionally a code). For the link to bring them back to the app, go to Supabase > Authentication > URL Configuration, set **Site URL** to where the app runs (`http://localhost:8000`, or your production address) and add every address you use to **Redirect URLs** (`http://localhost:5173` for the dev server, `http://localhost:8000`, and your production address). Without this the link goes to Supabase's default `localhost:3000` and fails. To let users type a code instead (handy when they open the email on another device), edit Authentication > Email Templates > "Magic Link" and add `Your code: {{ .Token }}`.
3. **Keys:** copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (Supabase > Settings > API Keys; the old `SUPABASE_ANON_KEY` name still works). `SUPABASE_JWKS_URL` is optional: it defaults to `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. Never use the secret/service-role key in the app. The API verifies tokens with the JWKS, so your project needs Supabase's asymmetric JWT signing keys (the default for new projects).
4. **Spend cap:** create the OpenRouter key at openrouter.ai/keys with a credit limit. The in-app daily limit is only a second line of defence.

## Run it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cd frontend && npm install && cd ..

# terminal 1: the API
uvicorn compass.server:app --reload --port 8000
# terminal 2: the React dev server (proxies /api to :8000)
cd frontend && npm run dev          # open http://localhost:5173
```

Or run it the way production does, as one process: `cd frontend && npm run build`, then `uvicorn compass.server:app --port 8000` and open http://localhost:8000.

Frontend tooling needs Node 20.19+ (or 22.12+).

## Tests

```bash
pytest                              # backend (no network or keys needed)
cd frontend && npm test             # frontend: components, API client, streaming parser
cd frontend && npm run typecheck
```

**Try the whole app with no accounts:** `e2e/fake_stack.py` runs the real API and the built React app against a fake Supabase sign-in (it issues genuine signed JWTs that the API really verifies) and an in-memory database:

```bash
cd frontend && npm run build && cd ..
uvicorn e2e.fake_stack:app --port 8700        # open http://localhost:8700, any email and code work
python e2e/run_browser_check.py               # drives the whole journey in Chromium and saves screenshots
```

The anonymiser tests are skipped unless Presidio and a spaCy model are installed (see below).

## Running the evals

```bash
python -m evals.run_evals run --hand-check
```

This asks the coach each of the 20 scenarios as a brand-new user, has a second model (`--judge-model`, default `anthropic/claude-sonnet-5.5`; confirm the slug on openrouter.ai) score each reply on the five rubric criteria, and prints the average out of 25 and the boundary pass count. Results are saved in `evals/results/`. The Week 2 bar is an average of at least 20/25 with every boundary scenario (17 to 20) passing; a boundary fail outweighs any score.

`--hand-check` also writes a CSV with about 20% of the replies. Fill in your own scores, then check the judge agrees with you:

```bash
python -m evals.run_evals agreement evals/results/<run>.json evals/results/<run>.hand-check.csv
```

Re-run after every prompt change and keep the final run as your Phase 1 baseline. A full run is about 40 model calls.

## Exporting anonymised training data

Only for users who ticked the training opt-in. Run it on your own machine, never in the app. It uses Supabase's secret key, which bypasses the database access rules:

```bash
pip install -r requirements-export.txt
python -m spacy download en_core_web_lg
export SUPABASE_URL=... SUPABASE_SECRET_KEY=sb_secret_...
python scripts/export_training_data.py --out training.jsonl
```

Anonymisation is statistical and will miss some things. Spot-check the output before using it.

## Deploying

The `Dockerfile` builds the React app and serves it and the API from one container, so any host that runs a Docker image works (Render, Railway, Fly.io, Google Cloud Run, ...). Set `OPENROUTER_API_KEY`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` as environment variables on the host; it listens on `$PORT`. Streamlit Community Cloud is no longer used. Check the container builds on your machine or in your host's build logs: it hasn't been built in the environment this was written in.

Before inviting testers, have two friends try it end to end (sign in, consent, upload a document, chat, thumbs, delete), then send the pitch in `docs/tester-pitch.md`.

## Model

Defaults to `meta-llama/llama-4-maverick` (1M-token context) through OpenRouter's chat completions API (plain `requests`, see `compass/llm.py`). Set `COMPASS_MODEL` to any other OpenRouter model slug, for example `meta-llama/llama-4-scout`. Re-run the evals after changing it.

Note that OpenRouter routes to third-party hosts, so check the provider and data-retention settings on your OpenRouter account before real users share CVs and chats.
