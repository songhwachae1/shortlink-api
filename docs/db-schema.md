# Database Schema — shortlink

## `users`

| Column            | Type             | Constraints                | Notes                                        |
| ----------------- | ---------------- | -------------------------- | -------------------------------------------- |
| `id`            | `bigserial`    | `PRIMARY KEY`            |                                              |
| `email`         | `citext`       | `NOT NULL`, `UNIQUE`   | case-insensitive comparison for login/signup |
| `password_hash` | `varchar(255)` | `NOT NULL`               |                                              |
| `first_name`    | `varchar(100)` | `NOT NULL`               |                                              |
| `last_name`     | `varchar(100)` | `NOT NULL`               |                                              |
| `created_at`    | `timestamptz`  | `NOT NULL DEFAULT now()` |                                              |
| `updated_at`    | `timestamptz`  | `NOT NULL DEFAULT now()` | maintained by `set_updated_at()` trigger     |

```sql
CREATE TABLE users (
    id              BIGSERIAL PRIMARY KEY,
    email           CITEXT NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    first_name      VARCHAR(100) NOT NULL,
    last_name       VARCHAR(100) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## `links`

| Column              | Type            | Constraints                  | Notes                                                                                    |
| ------------------- | --------------- | ---------------------------- | ---------------------------------------------------------------------------------------- |
| `id`              | `bigserial`   | `PRIMARY KEY`              | source sequence for code generation                                                      |
| `code`            | `varchar(16)` | `NOT NULL`, `UNIQUE`     | base62-encoded, derived from`id`. Required by every redirect, cache, and claim lookup. |
| `long_url`        | `text`        | `NOT NULL`                 | `text`, not `varchar` — URLs can exceed typical varchar limits                      |
| `user_id`         | `bigint`      | `NULL`, `FK → users.id ON DELETE SET NULL` | nullable — anonymous creation has no owner; set on claim                                |
| `is_active`       | `boolean`     | `NOT NULL DEFAULT true`    | drives partial index for fast redirect lookups; flipped to`false` on soft delete       |
| `deactivated_at`  | `timestamptz` | `NULL`                     | set when soft-deleted; cleared on reactivation/claim                                     |
| `click_count`     | `integer`     | `NOT NULL DEFAULT 0`       | lifetime total, never resets; incremented by fire-and-forget click tracker               |
| `last_clicked_at` | `timestamptz` | `NULL`                     | most recent click; drives the purge job's "cold" check.`NULL` until first click.       |
| `created_at`      | `timestamptz` | `NOT NULL DEFAULT now()`   |                                                                                          |
| `updated_at`      | `timestamptz` | `NOT NULL DEFAULT now()`   |                                                                                          |

```sql
CREATE TABLE links (
    id               BIGSERIAL PRIMARY KEY,
    code             VARCHAR(16) NOT NULL UNIQUE,
    long_url         TEXT NOT NULL,
    user_id          BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    is_active        BOOLEAN NOT NULL DEFAULT true,
    deactivated_at   TIMESTAMPTZ NULL,
    click_count      INTEGER NOT NULL DEFAULT 0,
    last_clicked_at  TIMESTAMPTZ NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Indexes

```sql
-- Full uniqueness on code is already enforced by the UNIQUE constraint above,
-- independent of is_active — a code is never reissued, active or not.

-- Per-user link listing (dashboard, "my links")
CREATE INDEX ix_links_user_id
    ON links (user_id)
    WHERE user_id IS NOT NULL;

-- Purge job scan
CREATE INDEX ix_links_purge_candidates
    ON links (last_clicked_at, created_at)
    WHERE is_active = true;
```

### Triggers

`users` and `links` each have a `BEFORE UPDATE ... FOR EACH ROW` trigger (`trg_<table>_set_updated_at`) that calls the shared `set_updated_at()` function to refresh `updated_at`. Created in the migrations (autogenerate does not detect them). The `citext` extension is also created by the users migration.

### Purge query (cold-link check)

A link is a purge candidate if it's had no activity in the last **90 days** — whether it was never clicked, or was clicked before but has since gone quiet:

```sql
SELECT id, code FROM links
WHERE is_active = true
  AND (
    last_clicked_at < now() - interval '90 days'
    OR (last_clicked_at IS NULL AND created_at < now() - interval '90 days')
  );
```

Matching rows are soft-deleted (`is_active = false`, `deactivated_at = now()`). After a further **30-day** grace period, a separate job archives (`deactivated_at < now() - interval '30 days'`) and hard-deletes.

### Cache key mapping (for reference)

| Redis key                      | Sourced from                                                          |
| ------------------------------ | --------------------------------------------------------------------- |
| `shorturl:{code}`            | `links.long_url` where `code` matches, `is_active = true`       |
| `shorturl:{code}:meta`       | `links.*` (metadata subset)                                         |
| `shorturl:{code}:clicks`     | buffer, flushed into`links.click_count` / `links.last_clicked_at` |
| `longurl:{user_id}:{hashed}` | `links.long_url` hashed, scoped to `links.user_id`                |
