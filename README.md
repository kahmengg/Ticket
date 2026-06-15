# Ticket Sale Assistant

Ticket Sale Assistant is a safe MVP backend for monitoring official event announcement pages, storing detected events, and sending Telegram alerts when new events are discovered.

It is intentionally conservative. It does not automate ticket purchases, join queues, log in to ticketing sites, bypass CAPTCHA, perform checkout actions, or scrape at high frequency.

## What it does

- Checks the Live Nation Singapore events page.
- Normalizes discovered event data.
- Stores events in SQLite with SQLAlchemy.
- Detects new, updated, and unchanged events.
- Sends Telegram alerts for newly discovered events when credentials are configured.
- Exposes a small FastAPI API for health, event listing, and manual checks.
- Optionally runs scheduled checks with APScheduler.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` if you want Telegram alerts or scheduler support.

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./ticket_assistant.db` | Local SQLite database URL. |
| `TELEGRAM_BOT_TOKEN` | empty | Telegram bot token. Notifications are skipped if missing. |
| `TELEGRAM_CHAT_ID` | empty | Single Telegram chat ID. Useful for one private user. |
| `TELEGRAM_CHAT_IDS` | empty | Comma-separated Telegram chat IDs for multiple private users. |
| `TELEGRAM_WEBHOOK_SECRET` | empty | Optional secret token checked on Telegram webhook requests. |
| `SCRAPE_INTERVAL_HOURS` | `6` | Minimum enforced value is 1 hour. |
| `REMINDER_INTERVAL_MINUTES` | `30` | How often to check the database for watchlist sale reminders. Does not scrape source sites. |
| `ENABLE_SCHEDULER` | `false` | Set to `true` to start periodic checks with the API process. |
| `SEND_ALERTS_ON_FIRST_RUN` | `false` | Seeds the initial event database without alerting old/current concerts. Set `true` only for testing. |
| `SALE_REMINDER_HOURS` | `24,1` | Comma-separated watchlist-only sale reminder windows. |
| `LIVENATION_SG_EVENTS_URL` | filtered Live Nation SG all-events URL | Source URL used by the Live Nation SG scraper. |

## Telegram private chats

For one user, set:

```env
TELEGRAM_CHAT_ID=123456789
```

For multiple private users, set:

```env
TELEGRAM_CHAT_IDS=123456789,987654321
```

Each user must start a private chat with your bot first by opening the bot in Telegram and pressing Start. To find a chat ID during development, send your bot a message, then open this URL in a browser with your real bot token:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
```

Look for `message.chat.id` in the JSON response.

The app also includes `POST /telegram/webhook`. When Telegram sends updates to this endpoint, the app stores:

- `chat.id`
- `from.id`
- `username`
- first and last name
- chat type

After that, future alerts are sent to stored active subscribers plus any chat IDs configured in `.env`.

Supported Telegram commands:

- `/start` subscribes the chat.
- `/upcoming` shows the next 5 upcoming concerts.
- `/latest` shows the 5 newest concerts discovered by the app.
- `/watch artist` watches an artist or event keyword.
- `/watchlist` shows watched keywords.
- `/unwatch artist` removes a watched keyword.
- `/stop` unsubscribes the chat.
- `/help` lists commands.

For local development, Telegram cannot call `http://127.0.0.1:8000` directly. To test the webhook locally, use a public HTTPS tunnel such as ngrok, then set the webhook with:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=https://YOUR_PUBLIC_URL/telegram/webhook&secret_token=YOUR_SECRET
```

## Run locally

```bash
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API docs.

## Run tests

```bash
pytest
```

## API endpoints

- `GET /health` returns API status.
- `GET /events` returns all stored events, newest first.
- `GET /events/upcoming` returns events with an event date or sale date in the future.
- `POST /run-check` manually runs the Live Nation SG scraper, stores results, and sends Telegram alerts for new events.
- `POST /telegram/test-message` sends a test message to configured or stored Telegram chat IDs.
- `POST /telegram/webhook` receives Telegram updates and stores subscribers.

## Docker

```bash
docker build -t ticket-sale-assistant .
docker run --rm -p 8000:8000 --env-file .env ticket-sale-assistant
```

## Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for the recommended Render + Supabase production setup.

## Assumptions

- Live Nation Singapore markup may change, so the scraper uses broad, easy-to-adjust selectors.
- Unknown date and sale information is stored as `null` until selectors are refined.
- SQLite is the local MVP database; production should move to Postgres.
- Scheduler checks default to every 6 hours and should stay conservative.

## Next steps

- Refine Live Nation SG selectors after inspecting real production markup.
- Add more official event sources behind the same scraper interface.
- Store alert send records in the `alerts` table.
- Add Alembic migrations.
- Migrate from SQLite to Supabase/Postgres for hosted deployment.
- Add deployment configuration for a small cloud runtime.
