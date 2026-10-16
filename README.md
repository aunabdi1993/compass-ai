# compass-ai

Career coach for people who are currently employed and want to grow: perform better in their role, build skills, win a promotion, or move to a better job.

Stack (chosen for speed): Python + Streamlit, Llama 4 Maverick (Meta) via OpenRouter, Supabase (login + database), Streamlit Community Cloud.

## Status: Phase 1, Weeks 1 and 2

Week 1 (core coach)
- Streaming chat using the Compass system prompt (`compass/prompts.py`)
- Supabase email login, one account per user, every conversation saved
- Profile page (role, industry, goals, pasted CV) injected into the prompt
- Memory: when a session ends the model writes a 5-line note; the last 5 notes go into the next session's prompt. If someone just closes the tab, the note is written the next time they log in.
- Per-user daily message limit as a cost guard (default 50, `MAX_USER_MESSAGES_PER_DAY`)

Week 2 (safe, and ready to test)
- **Documents:** users upload PDF, Word, text or Markdown files (CV, job description, review notes). Only the extracted text is kept. Each document can be switched on or off or removed, and the switched-on ones go into every conversation (newest first, up to 80,000 characters in total), so the coach's advice stays relevant. The coach refers to documents by name. Uploaded text is wrapped as data, so instructions hidden in a document are not followed.
- **Consent screen** on first login, with a separate, optional, default-off tick box for using anonymised chats in training. Nothing is loaded or sent to the model until the user agrees. Bump `CONSENT_VERSION` in `compass/consent.py` to ask everyone again.
- **Privacy page:** change the training opt-in, or **delete my data** (one atomic database call removing chats, summaries, documents, profile and consent record, then sign out).
- **Thumbs up/down** on every coach reply, saved on the message (`messages.feedback`: 1 or -1).
- **Anonymisation script** (`scripts/export_training_data.py`, using Microsoft Presidio) that exports only opted-in users' chats with names, emails, phone numbers, URLs, locations and company names replaced.
- **Evals:** the 20 scenarios and a runner that scores them with a second model against the rubric (`evals/`).

Not yet (Week 3): onboarding testers, monitoring, and the Phase 1 baseline score.

## Setup

1. **Supabase**: create a project, then run `database/schema.sql` in the SQL editor. It is safe to re-run. If you already ran the Week 1 version, run just `database/migrations/002_week2.sql`.
2. **Login email**: in Supabase go to Authentication > Email Templates > "Magic Link" and make the body include the code, e.g. `Your Compass sign-in code: {{ .Token }}`. The app asks users to type that code (Streamlit can't read the token from a magic-link redirect).
3. **Secrets**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in `OPENROUTER_API_KEY`, `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (Supabase > Settings > API Keys; formerly called the anon key, and the old `SUPABASE_ANON_KEY` name still works). Never use the secret/service-role key or the JWKS URL: the app refuses to start with a secret key, and it doesn't need JWKS because Supabase enforces access through Row Level Security. The file is git-ignored.
4. **Spend cap**: create an OpenRouter API key at openrouter.ai/keys and give it a credit limit. The in-app daily limit is only a second line of defence.
5. Run:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   streamlit run app.py
   ```

Tests (no network or keys needed): `pytest`. The anonymiser tests are skipped unless Presidio and a spaCy model are installed (see below).

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

Push to GitHub, create an app on Streamlit Community Cloud pointing at `app.py`, and paste the three secrets into its Secrets box. Cloud installs `requirements.txt` only, so Presidio is not deployed with the app. Then have two friends try it end to end (sign in, consent, upload a document, chat, thumbs, delete) before sending the pitch in `docs/tester-pitch.md`.

## Model

Defaults to `meta-llama/llama-4-maverick` (1M-token context) through OpenRouter's chat completions API (plain `requests`, see `compass/llm.py`). Set `COMPASS_MODEL` to any other OpenRouter model slug, for example `meta-llama/llama-4-scout`. Re-run the evals after changing it.

Note that OpenRouter routes to third-party hosts, so check the provider and data-retention settings on your OpenRouter account before real users share CVs and chats.
