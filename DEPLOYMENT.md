# Production Deployment

Recommended MVP production setup:

- App hosting: Render Web Service
- Database: Supabase Postgres
- Telegram subscriptions: webhook to `POST /telegram/webhook`

One Render web process serves the API. GitHub Actions triggers source checks and reminders; Supabase stores events, subscribers, and alert history.

## Why Render + Supabase

Render runs the included Dockerfile, which installs Python dependencies and the Chromium runtime used by website adapters:

```text
Runtime: Docker
Dockerfile Path: ./Dockerfile
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
Runtime: Docker
Dockerfile Path: ./Dockerfile
Health Check Path: /health
```

Or use the included `render.yaml` Blueprint.

4. Add environment variables in Render:

```env
DATABASE_URL=your_supabase_postgres_connection_string
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_WEBHOOK_SECRET=make_a_long_random_secret
RUN_CHECK_SECRET=make_a_different_long_random_secret
ENABLE_SCHEDULER=false
ENABLE_LIVENATION=true
ENABLE_TICKETMASTER=true
TICKETMASTER_API_KEY=your_ticketmaster_discovery_api_key
SCRAPE_INTERVAL_HOURS=6
REMINDER_INTERVAL_MINUTES=30
SEND_ALERTS_ON_FIRST_RUN=false
SALE_REMINDER_HOURS=24,1
```

Do not set `TELEGRAM_CHAT_ID` in production unless you want to force alerts to a fixed chat. Production users should subscribe through `/start` after the webhook is connected.

## External Schedule

Free Render web services sleep when idle, so APScheduler cannot guarantee six-hour checks by
itself. The included GitHub Actions workflow calls the app every six hours as a reliable trigger.
GitHub Actions is the production scheduling authority: source checks run every six hours and sale
reminders every half hour. Keep `ENABLE_SCHEDULER=false` in Render to prevent duplicate in-process
schedules. The in-process scheduler remains available for deployments without external scheduling.

In GitHub under **Settings > Secrets and variables > Actions**, configure:

```text
Repository variable:
TICKET_CHECK_URL=https://your-render-url.onrender.com

Repository secret:
RUN_CHECK_SECRET=same_value_as_render
```

After the Render service is redeployed, open GitHub Actions and manually run **Scheduled ticket
check** once. A successful run returns the `/run-check` JSON response. The recurring request wakes
Render and performs real Supabase database work, which also helps prevent Free Plan inactivity
pausing.

Scheduled workflows in public GitHub repositories are disabled after 60 days without repository
activity. For a permanently unattended setup, use a paid always-on service or a dedicated
external cron provider.

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
- `/upcoming` browses future concerts, nearest first, five per page.
- `/latest` browses latest concerts found, five per page; initial imports appear in an older section.
- `/watch artist` watches an artist or event keyword.
- `/watchlist` shows watched keywords.
- `/unwatch artist` removes a watched keyword.
- `/stop` unsubscribes the chat.
- `/help` lists commands.

Previous / Next edit the same message. Refresh reloads the catalogue; new discoveries are excluded
from an existing browsing session until refresh. Controls expire after 24 hours: rerun the command.
Browsing does not start scraping or reactivate a stopped subscription. The webhook registration
script explicitly enables `callback_query` updates; rerun it if an older webhook excludes them.

`/latest` uses discovery batches, not unverified website publication dates. Events found in the same
check have equal recency and sort by normalized title, performance date and ID. Existing records
remain labelled **Previously imported**, preserving their alert history. Adding a provider or editing
details does not reset discovery time. `/upcoming` excludes cancelled and postponed performances;
undated concerts with future sales follow dated performances.

## First Production Check

With:

```env
SEND_ALERTS_ON_FIRST_RUN=false
```

run:

```text
POST /run-check
Authorization: Bearer your_RUN_CHECK_SECRET
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

- Keep GitHub Actions as the sole production scheduling authority and check both workflow histories after deployment.
- A database lock prevents overlapping source jobs; alert uniqueness prevents ordinary repeated checks from resending unchanged changes. A crash after Telegram accepts a message can still cause a retry duplicate.
- Alembic is now configured. See `MIGRATIONS.md` before making future schema changes.
