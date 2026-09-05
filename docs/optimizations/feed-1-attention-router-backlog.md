# FEED-1 Optimization Backlog

Deferred findings from the FEED-1 tri-review (2026-09-05). Everything Critical/High
was fixed on the branch; what follows is Medium-and-below, kept because it is real
but not worth blocking the merge. Ordered by expected value.

## Worth doing in FEED-2

- **Click endpoint has no CSRF protection** (`api/feed.py`, `POST /feed/{id}/click`).
  The app has no auth and CORS is limited to `localhost:7860`, but a simple POST needs
  no preflight, so any page the user visits could forge clicks against `127.0.0.1:8000`.
  Impact today is a bogus `clicked_at`. **FEED-2 plans to feed click data into interest
  tuning, which turns this from a nuisance into a way to skew what the user is shown.**
  Fix before that lands, not after.

- **`FeedStore` is constructed per API request** (`api/feed.py:_store`), so
  `_init_schema` runs its `CREATE TABLE IF NOT EXISTS` + `commit()` on every `/feed`
  hit — a write lock on a read path. Every other store in the project is a cached
  module-level dependency in `api/dependencies.py`. The per-request lifetime does
  sidestep the cross-process problems this project has been burned by before
  (ChromaDB), so this is a deliberate-looking choice that should either be made
  explicit in a comment or converted to `get_feed_store()`.

- **Retry-on-`DatabaseError` doesn't help with lock contention.** `_run`/`_run_many`
  catch `sqlite3.DatabaseError`, which includes `OperationalError: database is locked`.
  Reconnecting does not clear a writer lock, so the retry fires immediately and raises,
  short-circuiting the 5s `busy_timeout` rather than respecting it. Narrow the catch,
  or add a short backoff.

## Cheap cleanups

- **`FeedSectionResponse.items` is `list[dict[str, str]]`.** The `{url, title, take}`
  shape is enforced only by a comment, and the generated OpenAPI schema is
  `additionalProperties: string`. Promote to a `FeedSectionItem(BaseModel)` — the
  frontend already declares the proper interface.

- **`_feed_counts` opens `feed.db` on the briefing path** while `FeedBlock` opens it
  again via `/feed`, so a Today-surface load touches the db twice. Different payloads,
  so it's defensible; noted for whoever wonders.

- **Sequential RSS fetching.** Eight sources, one after another, ~14s wall clock. Fine
  for a cron job, and concurrency would add real complexity. Revisit only if the source
  list grows well past the current 50-source cap.

- **Micro-inefficiencies with no measurable impact at this scale:** `select_top_n`
  rebuilds its filtered list per type; `FeedBlock`/`feed/page.tsx` recompute their
  derived maps on every render without `useMemo`. Listed for completeness — not
  recommended.

## Deliberately not doing

- **SSRF hardening beyond the scheme allowlist.** Feed URLs are user-configured, so
  pointing one at loopback is self-inflicted. Redirects are followed, so a feed host
  that goes bad could in principle 302 to the LAN — but urllib refuses non-http(s)
  redirect targets and the response still has to parse as a feed. The `_is_safe_link`
  check on `source.url` plus the size cap closes the practical exposure.

- **`anthropic_api_key` as `SecretStr`.** Pre-existing project-wide pattern in
  `config.py`, not FEED-1's to change.
