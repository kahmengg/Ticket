# Changes

## 2026-10-08

- Watched concerts now receive reminders for named presales as well as general sales.
- Alerts use compact ticket/calendar buttons with previews disabled. Past sales no longer offer
  calendar actions; concert calendar duration is labelled approximate.
- New discoveries say “Concert found”. Updates identify the changed fields, and link-only or
  punctuation-only changes do not generate an update alert.
- Future off-sale listings use understandable availability wording. Explicit provider withdrawals
  clear stale dates, while missing extraction data preserves the last known values.
- Long messages are bounded; permanently rejected deliveries stop retrying. Delayed broad-window
  reminders yield to an applicable shorter reminder to avoid sending both together.
- GitHub reminder runs report overdue cadence. Replacement scheduling awaits Vault configuration
  and verification; see REMINDER_SCHEDULING.md. Existing scheduling remains active.
- Supabase source listings and sale windows now have row-level security enabled, closing public
  API exposure while preserving the trusted backend's database access.
