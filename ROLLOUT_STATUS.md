# Telegram browsing rollout — 10 September 2026

Implemented and pushed to `main` in three phases:

- `b19125c`: discovery metadata, additive migration and stable latest/upcoming ordering.
- `46fb768`: signed Previous / Next / Refresh controls and compact pages.
- `cb62fab`: GitHub-only production scheduling, exact venue aliases, query checks and duplicate audit.

Verification completed:

- Local suite: 130 passed; PostgreSQL integration test skipped locally.
- GitHub CI: 131 passed, including PostgreSQL migration and container checks (run 34440508449).
- Render deployment `dep-dah9qseq1p3s73b7pa60` is live on `cb62fab`.
- Render's saved `ENABLE_SCHEDULER` value was explicitly verified as `false` after deployment.
- Final source workflow 34475219391 succeeded: Live Nation 25, Ticketmaster Discovery 62;
  zero new events, zero updated events, 73 unchanged events, zero notifications.
- Final reminder workflow 34475214761 succeeded with zero notifications.
- An authenticated owner-only `/latest` request succeeded. Awaiting the owner's confirmation
  that Next, Previous and Refresh operate correctly in the real Telegram chat.

Existing subscriptions, watchlists and alert history were retained. See `DUPLICATE_AUDIT.md`
for historical duplicate candidates; they were not automatically merged. True website publication
ordering, fuzzy merging, a web dashboard and extra caching infrastructure remain deferred.

Resume point: follow up on the owner's live button test; if it fails, inspect Telegram callback
delivery and the webhook's allowed update types. No additional implementation phase is pending.
