# Production Deployment

Recommended MVP production setup:

- App hosting: Render Web Service
- Database: Supabase Postgres
- Telegram subscriptions: webhook to `POST /telegram/webhook`

This keeps the app simple: one web process runs the API and scheduler, and Supabase stores events, subscribers, and alert history.

## Why Render + Supabase

Render can run this FastAPI app directly from the repository with:

```text
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Supabase gives you a managed Postgres database, which is a better production fit than local SQLite.

## Database Setup

1. Create a Supabase project.
2. Go to the Supabase project dashboard.
3. Open **Connect**.
4. Copy a Postgres connection string.

For this app, use the **Session pooler** connection string when available. It usually looks like:

```text
postgres://postgres.PROJECT_REF:PASSWORD@aws-REGION.pooler.supabase.com:5432/postgres
```

If your connection string does not include SSL mode and the connection fails, append:

```text
?sslmode=require
```

Use the full value as:

```env
DATABASE_URL=postgres://...
```

The app automatically converts `postgres://` / `postgresql://` into the SQLAlchemy driver URL it needs.

## Should You Move The Local SQLite Database?

Recommended: do **not** migrate your local SQLite data for the first production deploy.

Reason: the current local database mostly contains test runs and current event baseline data. In production, use:

```env
SEND_ALERTS_ON_FIRST_RUN=false
```

Then the first production `/run-check` will seed current concerts silently. Future new or changed concerts will alert users.

Only migrate SQLite if you intentionally want to preserve local subscribers or alert history. For this MVP, a clean Supabase database is simpler and safer.

## Render Setup

1. Push this project to GitHub.
2. In Render, create a new **Web Service** from the GitHub repo.
3. Use these settings:

```text
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Health Check Path: /health
```

Or use the included `render.yaml` Blueprint.

4. Add environment variables in Render:

```env
PYTHON_VERSION=3.12.13
DATABASE_URL=your_supabase_postgres_connection_string
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_SECRET=make_a_long_random_secret
ENABLE_SCHEDULER=true
SCRAPE_INTERVAL_HOURS=6
REMINDER_INTERVAL_MINUTES=30
SEND_ALERTS_ON_FIRST_RUN=false
SALE_REMINDER_HOURS=24,1
```

Do not set `TELEGRAM_CHAT_ID` in production unless you want to force alerts to a fixed chat. Production users should subscribe through `/start` after the webhook is connected.

## Telegram Webhook Setup

After Render deploys, your app URL will look like:

```text
https://ticket-sale-assistant.onrender.com
```

Set the webhook by running this locally:

```powershell
$env:TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
$env:TELEGRAM_WEBHOOK_SECRET="same_secret_as_render"
$env:PUBLIC_BASE_URL="https://your-render-url.onrender.com"
.venv\Scripts\python.exe scripts\set_telegram_webhook.py
```

Then open your Telegram bot and send:

```text
/start
```

The app should save your chat and reply with a subscription confirmation.

Available Telegram commands after the webhook is connected:

- `/start` subscribes the chat.
- `/upcoming` shows the next 5 upcoming concerts.
- `/latest` shows the 5 newest concerts discovered by the app.
- `/watch artist` watches an artist or event keyword.
- `/watchlist` shows watched keywords.
- `/unwatch artist` removes a watched keyword.
- `/stop` unsubscribes the chat.
- `/help` lists commands.

## First Production Check

With:

```env
SEND_ALERTS_ON_FIRST_RUN=false
```

run:

```text
POST /run-check
```

Expected first production result:

```json
{
  "new_events": 22,
  "updated_events": 0,
  "unchanged_events": 0,
  "notifications_sent": 0
}
```

That is correct. It seeds the baseline without spamming old/current concerts.

Future checks should alert only genuinely new or changed events.

## Production Notes

- Keep only one scheduled instance running. If you scale the Render service above one instance, the scheduler may run more than once.
- For a larger production setup, move the scheduler into a separate worker or cron job.
- Add Alembic migrations before making frequent schema changes.
