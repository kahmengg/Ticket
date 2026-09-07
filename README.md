# Ticket Sale Assistant

Ticket Sale Assistant is a production-deployed concert alert assistant. It monitors official event announcement data, stores concerts in a database, detects new or changed events, and sends Telegram alerts with ticket sale reminders.

The project is intentionally safe and conservative. It does **not** automate ticket purchasing, queue joining, account login, checkout, CAPTCHA solving, queue bypassing, or high-frequency scraping.

## Features

- Monitors Live Nation Singapore event data.
- Stores events, subscribers, watchlists, and alert history.
- Detects new, updated, and unchanged concerts.
- Sends Telegram alerts for new and changed concerts.
- Prevents first-run spam by seeding existing concerts silently in production.
- Prevents duplicate alerts per chat and event.
- Supports Telegram subscriptions through `/start`.
- Supports user watchlists with `/watch`, `/watchlist`, and `/unwatch`.
- Sends watchlist-only ticket sale reminders.
- Includes Google Calendar links for both concert dates and ticket sale dates.
- Provides FastAPI endpoints for health checks, event listing, manual checks, and Telegram webhook handling.
- Runs scheduled checks with APScheduler.
- Supports SQLite locally and Supabase/Postgres in production.
- Uses Alembic for database migrations.

## Telegram Commands

```text
/start              Subscribe this chat
/upcoming           Show the next 5 upcoming concerts
/latest             Show the 5 newest concerts discovered
/watch artist       Watch an artist or event keyword
/watchlist          Show watched keywords
/unwatch artist     Remove a watched keyword
/stop               Unsubscribe this chat
/help               Show available commands
```

Watchlist matching is case-insensitive and mostly ignores spacing/punctuation. For example, these can match the same artist:

```text
/watch big bang
/watch BIGBANG
/watch bigbang
/watch Big-Bang
```

Ticket sale reminders are watchlist-only. A user receives sale reminders only for concerts matching their watched keywords.

## Alert Messages

Full event alerts include:

```text
BABYMONSTER WORLD TOUR [춤 (CHOOM)] IN SINGAPORE
Venue: Singapore Indoor Stadium
Event date: 2026-11-28T10:00:00
Sale date: 2026-06-11T04:00:00
URL: https://www.livenation.sg/...
Add concert to calendar: https://calendar.google.com/...
Add ticket sale to calendar: https://calendar.google.com/...
```

Compact Telegram commands like `/upcoming` and `/latest` do not include calendar links so chat replies stay readable.

## Tech Stack

- Python 3.12
- FastAPI
- SQLAlchemy ORM
- Alembic
- SQLite for local development
- Supabase/Postgres for production
- APScheduler
- Requests
- Telegram Bot API
- Pytest
- Render deployment

## Project Structure

```text
app/
  api/routes.py
  config.py
  crud.py
  database.py
  main.py
  models.py
  scheduler.py
  schemas.py
  scrapers/
  services/
alembic/
  versions/
scripts/
tests/
```

## Local Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your local settings.

Run the app:

```powershell
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

Run tests:

```powershell
pytest
```

## Environment Variables

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./ticket_assistant.db` | SQLite locally, Supabase/Postgres in production. |
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token. |
| `TELEGRAM_CHAT_ID` | empty | Optional single fixed chat ID for local testing. |
| `TELEGRAM_CHAT_IDS` | empty | Optional comma-separated fixed chat IDs. |
| `TELEGRAM_WEBHOOK_SECRET` | empty | Required for webhook requests; missing configuration returns HTTP 503. |
| `RUN_CHECK_SECRET` | empty | Required bearer token for the scheduled `/run-check` endpoint. |
| `SCRAPE_INTERVAL_HOURS` | `6` | How often to fetch source event data. Minimum is 1 hour. |
| `REMINDER_INTERVAL_MINUTES` | `30` | How often to check the database for watchlist sale reminders. Does not scrape source sites. |
| `ENABLE_SCHEDULER` | `false` | Set to `true` in production. |
| `SEND_ALERTS_ON_FIRST_RUN` | `false` | Seeds existing concerts without alerting old/current events. Set `true` only for testing. |
| `SALE_REMINDER_HOURS` | `24,1` | Comma-separated watchlist-only sale reminder windows. |
| `LIVENATION_SG_EVENTS_URL` | filtered Live Nation SG URL | Source URL used to derive Live Nation filters. |

## API Endpoints

- `GET /health` returns API status.
- `GET /events` returns all stored events, newest first.
- `GET /events/upcoming` returns upcoming events.
- `POST /run-check` runs the Live Nation SG check with `Authorization: Bearer <RUN_CHECK_SECRET>`.
- `POST /telegram/test-message` sends a Telegram test message with `Authorization: Bearer <RUN_CHECK_SECRET>`. Returns `configured_chat_count` and `sent`, without exposing chat IDs.
- `POST /telegram/webhook` receives Telegram updates and handles bot commands. Requires `X-Telegram-Bot-Api-Secret-Token` matching `TELEGRAM_WEBHOOK_SECRET`; missing configuration returns HTTP 503 and invalid credentials return HTTP 403.

## Telegram Webhook

Production users subscribe through Telegram by sending:

```text
/start
```

After deploying to a public HTTPS URL, set the webhook:

```powershell
$env:TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
$env:TELEGRAM_WEBHOOK_SECRET="same_secret_as_render"
$env:PUBLIC_BASE_URL="https://your-render-url.onrender.com"
.venv\Scripts\python.exe scripts\set_telegram_webhook.py
```

For local development, Telegram cannot call `http://127.0.0.1:8000` directly unless you use a public tunnel such as ngrok.

## Scheduled Production Checks

The GitHub Actions workflow in `.github/workflows/scheduled-ticket-check.yml` calls the secured
`/run-check` endpoint every six hours. This wakes a sleeping Render service, runs the scraper,
and generates genuine Supabase database activity.

Configure these values before enabling the workflow:

1. In Render, add `RUN_CHECK_SECRET` with a long random value.
2. In GitHub, open **Settings > Secrets and variables > Actions**.
3. Add the repository variable `TICKET_CHECK_URL` with the Render service URL, for example
   `https://ticket-sale-assistant.onrender.com`.
4. Add the repository secret `RUN_CHECK_SECRET` with exactly the same value used in Render.
5. Redeploy Render, then run **Scheduled ticket check** manually once from the GitHub Actions page.

The endpoint fails closed with HTTP 503 when `RUN_CHECK_SECRET` is not configured and rejects
incorrect credentials with HTTP 401.

GitHub automatically disables scheduled workflows in public repositories after 60 days without
repository activity. Make a repository update within that period or move this schedule to a
dedicated cron provider for unattended long-term operation.

## Deployment

Recommended production setup:

- Render Web Service for the FastAPI app.
- Supabase Postgres for the database.

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full deployment steps.

## Database Migrations

Alembic is configured for versioned database schema changes.

Common commands:

```powershell
.venv\Scripts\alembic.exe current
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"
```

See [MIGRATIONS.md](./MIGRATIONS.md) for the full workflow.

## Docker

Docker is available but not required for the recommended Render Python runtime deployment.

```powershell
docker build -t ticket-sale-assistant .
docker run --rm -p 8000:8000 --env-file .env ticket-sale-assistant
```

## Safety Boundaries

This app only monitors official event announcement data and sends notifications.

It does not:

- buy tickets
- join queues
- log in to ticketing accounts
- bypass CAPTCHA
- automate checkout
- scrape aggressively

## Future Improvements

- Add more official event sources.
- Add a small admin dashboard.
- Add richer user preferences.
- Add better production observability and alert failure reporting.
