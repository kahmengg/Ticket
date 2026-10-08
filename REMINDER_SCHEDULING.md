# Reminder scheduling cutover

Status: **configured and verified** in Ticket (`juasihdpmrqhirbcgpmx`).
Supabase job `ticket-sale-reminders` checks reminders at minutes 7 and 37 each hour.
The existing Render credential is encrypted in Vault as `ticket_run_check_secret`.
Two temporary one-minute scheduled calls returned HTTP 200 with `notifications_sent: 0`
at 14:01 and 14:02 UTC on October 8, 2026, before switching to the half-hour cadence.
GitHub's automatic reminder trigger is removed; its manual fallback remains available.
Source checks remain on GitHub every six hours. Subscriber, watchlist and alert records are retained.

GitHub's configured `7,37 * * * *` schedule produced runs hours apart on October 6–8.
This is a trigger-cadence problem, not evidence of failed application jobs. GitHub documents
that scheduled events may be delayed or dropped. `scripts/check_schedule_gap.py` remains a
diagnostic helper for the previous GitHub schedule, not a monitor of Supabase Cron.

To reproduce or repair the configuration:

1. Open Ticket's dashboard. Inspect existing cron jobs first to avoid duplicates.
2. Enable Supabase Cron (`pg_cron`) and async HTTP (`pg_net`). Store the existing Render
   `RUN_CHECK_SECRET` in Supabase Vault as `ticket_run_check_secret`, without putting it in Git.
3. Schedule the SQL below every half hour. Do not run it until the Vault secret exists.
4. Verify the actual HTTP result in `net._http_response`, not just the cron job's SQL success.
   Require two scheduled HTTP 200 responses and a successful app reminder result.
5. Remove only the `schedule` trigger from `scheduled-reminders.yml`; retain its manual trigger
   and keep source checks on GitHub every six hours. Keep Render `ENABLE_SCHEDULER=false`.

```sql
-- Run as the project administrator. The cron command references Vault, never a literal secret.
select cron.schedule('ticket-sale-reminders', '7,37 * * * *', $job$
  select net.http_post(
    url := 'https://ticket-bj1i.onrender.com/run-reminders',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer ' || (
        select decrypted_secret from vault.decrypted_secrets
        where name = 'ticket_run_check_secret'
      )
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 120000
  );
$job$);
```

The database must remain active for Cron to run. This configuration is not a guarantee against
provider outages. Check job history and HTTP responses after cutover; add an independent heartbeat
service only if the project needs a stronger delivery guarantee.

References: https://supabase.com/docs/guides/cron/quickstart and
https://docs.github.com/en/actions/how-tos/troubleshoot-workflows
