# My Notepad – Flask App

A simple, password-protected notepad with folders and public/private notes.

## Features
- Email/password authentication (hashed passwords)
- Your name appears in the navbar and pages (personalize via Profile)
- Create folders and subfolders
- Create notes, move them into folders
- Toggle notes public/private; public notes get a shareable URL `/p/<slug>`
- "Remember me" style login (30-day session)
- SQLite by default; can switch to Postgres via `DATABASE_URL`

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask --app app.py run  # initializes db automatically on first run
```

## Deploy (Render.com example)
1. Create a new **Web Service** from this repo/zip.
2. Set **Build Command**: `pip install -r requirements.txt`
3. Set **Start Command**: `gunicorn app:app`
4. Add Environment Variables:
   - `SECRET_KEY` = a long random string
   - `DATABASE_URL` = leave default for SQLite, or use your Postgres URL (recommended for production)
5. Deploy. Visit the public URL to sign up and use your notepad.

## Security notes
- Always set a strong `SECRET_KEY` in production.
- Prefer Postgres (managed by Render) over SQLite for multi-user production.
- For custom domains + HTTPS, configure in your hosting provider.
