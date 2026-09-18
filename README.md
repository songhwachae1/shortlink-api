# shortlink-api

A URL shortener API with public (anonymous) and member-only features, built around a cache-aside read path and a sequence-based short code generator.

## Stack

- **FastAPI** — web framework
- **SQLAlchemy** + **Alembic** — ORM and migrations
- **PostgreSQL** — source of truth
- **Redis** — cache, rate limiting, click buffering
- **Docker** — containerization

## Design Overview

### Short code generation

Short codes are generated from a **PostgreSQL sequence**, base62-encoded. Postgres is the source of truth for the sequence — not Redis — so a Redis restart or data loss can never cause a duplicate code to be issued. Codes are assigned once, monotonically, and are never reused or reclaimed, even after a link is deleted.

### Redirect semantics

Redirects return **302 (Found)**, not 301. This is deliberate: a 301 gets cached by browsers/CDNs as permanent, which would break the ability to edit, deactivate, or track clicks on a link after the fact.

### Caching (cache-aside)

Redis is used as a cache in front of Postgres for the redirect path, keyed as:

| Key                             | Purpose                              |
| ------------------------------- | ------------------------------------ |
| `shorturl:{code}`             | cached long URL for redirect lookups |
| `shorturl:{code}:meta`        | cached link metadata                 |
| `shorturl:{code}:clicks`      | click counter buffer                 |
| `longurl:{user_id}:{hashed}`  | per-user dedup lookup                |
| `ratelimit:{ip}:{route}`      | anonymous rate limiting              |
| `ratelimit:{user_id}:{route}` | authenticated rate limiting          |

**Short codes carry a 24h TTL in Redis.** This is a cache expiry only — it does **not** mean the short link stops working. On a cache miss, the redirect falls through to Postgres, resolves normally, and repopulates the cache. Short links resolve indefinitely at the application level; only the cache entry expires.

### Click tracking

Click counting is **fire-and-forget** — it never blocks the redirect response. The redirect is issued first; click increment/logging happens as a background task.

### Read/write traffic profile

URL shorteners are structurally read-heavy: one write (creation) can generate an unbounded number of reads (redirects) over a link's lifetime. Write throughput (creation, update, delete) is expected to stay low even at meaningful scale, which shapes several decisions below — most notably, no rate limiting on redirects, and a simple fixed-window limiter on writes.

## Public vs. Member Features

**v1 ships public (anonymous) link creation first.** Anonymous users can create short links with no login. Editing, deleting, and setting a deactivation date are **member-only** features, gated behind authentication and ownership checks.

| Feature                 | Anonymous | Authenticated   |
| ----------------------- | --------- | --------------- |
| Create link             | ✅        | ✅              |
| Redirect                | ✅        | ✅              |
| Edit / delete link      | ❌        | ✅ (owner only) |
| Set deactivation date   | ❌        | ✅ (owner only) |
| Claim an anonymous link | —        | ✅              |

### Deduplication

Deduplication (same long URL → same code) is **per-user**, keyed as `longurl:{user_id}:{hashed}`. Anonymous creation is **not deduplicated** — every anonymous request for the same long URL gets a new code.

This is intentional: a global dedup key would mean unrelated users sharing the same generated code, which breaks ownership the moment one of them edits or deletes it, and pollutes click analytics with traffic from users who have nothing to do with each other. Scoping dedup to `owner_id` keeps every code single-owner and safe to mutate.

### Claiming an anonymous link

After signing up or logging in, a user can claim a link they created anonymously if they still have the short code:

```
POST /links/{code}/claim
```

- Succeeds only if the link is currently unowned (`owner_id IS NULL`)
- Fails with `409 Conflict` if already owned
- Fails with `404` if the code doesn't exist
- No proof of authorship is required beyond knowing the code — this is accepted as low risk, since an unclaimed link is just a redirect target, not sensitive data
- Claiming a link that is currently soft-deleted (see Purging below) also reactivates it: `owner_id` is set and `is_active` is restored to `true` in the same operation

## Authentication

- **JWT, ES256** (asymmetric signing)
- **Access token TTL: 15 minutes**
- **Refresh token TTL: 7 days**
- Access token payload carries at minimum `sub` (user id) and `exp`
- Signing key pair is supplied via environment/secrets at runtime — never baked into the Docker image

## Rate Limiting

**Algorithm: fixed window counter**, via Redis `INCR` + `EXPIRE`. Chosen for simplicity given the low-write-traffic profile of this service; the known weakness (burst at window boundaries) is not a meaningful risk at this scale.

| Route                                  | Limited?     | Key                                                                        |
| -------------------------------------- | ------------ | -------------------------------------------------------------------------- |
| `POST /shorten` (create)             | ✅           | `ratelimit:{ip}:{route}` (anon) / `ratelimit:{user_id}:{route}` (auth) |
| `GET /{code}` (redirect)             | ❌           | —                                                                         |
| `PATCH` / `DELETE` (update/delete) | ❌ (for now) | key reserved for future use                                                |

Redirects are unlimited — legitimate traffic on a popular link is bursty by nature, and limiting it would break the service's core purpose. Update/delete are unlimited for now because they require authentication and ownership, which already bounds the blast radius of abuse to an account's own links; the rate-limit key format (`{ip|user_id}:{route}`) is left in place so a limit can be added later without a schema change.

## Input Validation

- **Scheme allowlist**: only `http` and `https` accepted as the target URL scheme
- **Private IP / SSRF protection**: target URLs resolving to private, loopback, or link-local ranges (including the `169.254.169.254` cloud metadata range) are rejected at creation time
- This check happens at **creation time only**. Since DNS is attacker-controllable, a domain could in principle resolve differently at redirect time (DNS rebinding). This is a known, accepted limitation at the current scope.

## Cache Invalidation

On link update or delete, the corresponding `shorturl:{code}` and `shorturl:{code}:meta` cache entries are invalidated immediately. The redirect path never writes to link state — status changes only happen through explicit, authenticated write endpoints.

## Purging Policy

Low-engagement links are removed via a staged **archive-then-delete** pipeline, not an immediate hard delete:

1. **Soft delete** — a scheduled job flags links with 0 clicks in the last **90 days** (`is_active = false`, `deactivated_at = now()`)
2. **Grace period** — the link stays soft-deleted for another **30 days**. During this window:
   - Redirect requests to the link return `410 Gone`
   - The owning user can request reactivation
   - Anonymous links have no reactivation path (no owner to request it), unless claimed during the grace period, which reactivates them as a side effect
3. **Archive** — after the grace period, the link record is written to a file and removed from the primary `links` table
4. **Hard delete** — the row is deleted from Postgres

Hard delete (rather than a permanent soft-delete flag) is used deliberately: with sequence-based code generation, deleting a row never risks a code being reissued or recycled, so there's no correctness reason to keep dead rows around indefinitely. Soft-deleting alone would not reduce database size or index size, since the row and its index entries remain until the row is actually removed.

**Known limitation:** archiving to a flat file requires the file to live on a mounted volume in Docker (not container-local storage), and the current design has no rotation or concurrent-write handling for the archive file. Acceptable at current scope; worth revisiting if usage grows.

## Non-Goals (v1)

- Custom aliases / user-chosen short codes
- Permanence guarantees — links are subject to the purge policy above
- DNS-rebinding-proof SSRF protection (creation-time validation only)

## API (summary)

| Method     | Path                    | Auth             | Description                                 |
| ---------- | ----------------------- | ---------------- | ------------------------------------------- |
| `POST`   | `/shorten`            | optional         | Create a short link                         |
| `GET`    | `/{code}`             | none             | Redirect to the target URL                  |
| `PATCH`  | `/links/{code}`       | required (owner) | Update a link's target or deactivation date |
| `DELETE` | `/links/{code}`       | required (owner) | Delete a link                               |
| `POST`   | `/links/{code}/claim` | required         | Claim an anonymously-created link           |

## Running Locally

```bash
docker compose up --build
```

*(fill in environment variables, migration commands, and service ports here)*
