# compass-ai

Career coach for people who are currently employed and want to grow: perform better in their role, build skills, win a promotion, or move to a better job.

Stack (chosen for speed): Python + Streamlit, Claude API, Supabase (login + database), Streamlit Community Cloud.

## Status: Phase 1, Week 1 (core coach)

- Streaming chat using the Compass system prompt (`compass/prompts.py`)
- Supabase email login, one account per user
- Every conversation saved to the database
- Profile page (role, industry, goals, pasted CV) injected into the prompt
- Simple memory: when a session ends, the model writes a 5-line note; the last 5 notes go into the next session's prompt. If someone just closes the tab, the note is written the next time they log in.
- Per-user daily message limit as a cost guard (default 50, `MAX_USER_MESSAGES_PER_DAY`)

Not yet (Week 2+): consent screen, delete-my-data, anonymisation, thumbs up/down, evals.

## Setup

1. **Supabase**: create a project, then run `supabase/schema.sql` in the SQL editor.
2. **Login email**: in Supabase go to Authentication > Email Templates > "Magic Link" and make the body include the code, e.g. `Your Compass sign-in code: {{ .Token }}`. The app asks users to type that code (Streamlit can't read the token from a magic-link redirect).
3. **Secrets**: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill it in. Use the Supabase **anon** key, never the service key. The file is git-ignored.
4. **Spend cap**: set a monthly limit in the Anthropic Console (Settings > Limits). The in-app daily limit is only a second line of defence.
5. Run:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   streamlit run app.py
   ```

Tests (no network or keys needed): `pytest`

## Deploying

Push to GitHub, create an app on Streamlit Community Cloud pointing at `app.py`, and paste the secrets into its Secrets box.

## Model

Defaults to `claude-opus-5-5`. Set `COMPASS_MODEL` to change it (for example `claude-sonnet-5-5` to cut cost). Re-run the evals after changing it.
