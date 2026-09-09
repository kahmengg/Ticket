# Multi-source deployment

## Ticketmaster access diagnosis (9 September 2026)

The Render service is now Docker and Chromium installs successfully. An identified catalogue request succeeds locally (HTTP 200, 18 initial public detail links), while the deployed scraper receives HTTP 403 before extracting events. This establishes environment-dependent access rejection; it does not establish the exact IP, browser or security rule used by Ticketmaster. Changing database settings cannot address this failure.

The official Discovery API adapter activates when `TICKETMASTER_API_KEY` is set. Obtain a Consumer Key from https://developer.ticketmaster.com/products-and-docs/tutorials/events-search/search_events_with_discovery_api.html and enter it privately in Render Environment. Save and redeploy, then run Scheduled ticket check. No key is committed or printed in errors. The adapter queries Singapore music events with bounded pagination and retains dates, presales, prices and status where provided.

Singapore is a documented country filter, but that does not guarantee ticketmaster.sg catalogue coverage. A live comparison requires a user-owned key. An empty response remains an explicit error and does not complete a silent baseline. API observations use the separate `Ticketmaster Discovery Singapore` source identity and match Live Nation performances conservatively. Do not switch between API and website IDs under the same source identity.

Until a key and coverage are verified, the website source remains enabled and its 403 stays visible. Live Nation and reminder checks continue independently.

1. Back up the existing Postgres database before deploying. Startup upgrades Alembic to `20260908_0004`, preserving event IDs, subscribers and sent alerts. The source-listing migration requires a backup restore to reverse.
2. Build the repository Dockerfile. It installs Python 3.12, Chromium and Linux browser dependencies. `render.yaml` describes a Docker web service; an existing native Python service may require migration in Render. A Git push alone does not confirm that its runtime changed.
3. Retain the existing `DATABASE_URL`, Telegram token, webhook secret and `RUN_CHECK_SECRET`. Enable both provider flags. Keep `SEND_ALERTS_ON_FIRST_RUN=false` to seed Ticketmaster silently. Never put credentials in Git.
4. Confirm `/health` succeeds and the deployed OpenAPI schema contains `/sources/status` and `/run-reminders`. Call protected `/sources/status` with the bearer secret to inspect source results after a normal check. A source check can take several minutes.
5. Keep GitHub's `TICKET_CHECK_URL` variable pointed at the deployed service and its `RUN_CHECK_SECRET` identical to Render. The six-hour ticket workflow fetches both providers; the half-hour reminder workflow only reads stored events and retries pending notifications.
6. Check that both sources report `ok` after the first completed run. Unknown sale years appear as warnings and remain unknown; partial fetches fail the ticket workflow while preserving usable data from other pages/providers.

Use `python scripts/preview_sources.py` for extraction validation without touching production data or sending messages. CI verifies tests, Postgres migration/locking, and a Docker browser/startup smoke test. Schedules can be delayed; this is an announcement monitor, not real-time inventory or a guaranteed reminder delivery service.
