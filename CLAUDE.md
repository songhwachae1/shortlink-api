# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project state

This is an early-stage scaffold, not the full system described in README.md. Treat the README as the target design, not current behavior. As of now:

- `src/shortlink_api/main.py` and `src/shortlink_api/__init__.py` are **empty** — no FastAPI `app` instance exists yet, and the `shortlink-api` console script (`pyproject.toml` → `shortlink_api:main`) has no entry point to call.
- `src/shortlink_api/api/auth.py` is **empty** — no endpoints are wired up yet. `dependency.py`'s `get_current_user` assumes a route at `auth/login` (via `OAuth2PasswordBearer(tokenUrl="auth/login")`) that doesn't exist yet.
- Only `core/security` (JWT issuance/verification, bcrypt password hashing) and `config.py` (Pydantic settings) are implemented.
- Dependencies installed so far: `fastapi[standard]`, `bcrypt`, `pyjwt`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`. Postgres runs via `docker-compose.yml`. Redis is **not yet added**. The `users`/`links` models and baseline migrations (0001, 0002) exist; no repositories/services use them yet.
- No test suite, linter, or type checker is configured yet (no pytest/ruff/mypy in the lockfile, nothing under `[tool.*]` in `pyproject.toml`).

Don't assume infrastructure exists just because the README or db-schema doc describes it — check the actual code/deps first.

## Commands

Dependency management is via `uv` (`uv.lock` present, `pyproject.toml` uses `uv_build`).

```bash
uv sync              # install dependencies into .venv
uv run <script>       # run a script inside the project's venv
uv add <package>       # add a new dependency
uv run alembic upgrade head                            # apply migrations
uv run alembic revision --autogenerate -m "msg"       # new migration from models
uv run alembic check                                   # detect model/DB drift
```

There are no build, lint, or test commands yet — none are configured in `pyproject.toml`. When adding the first tests, add the corresponding tool (e.g. pytest) as a dependency and record the run command here.

## Architecture

- **Package layout**: `src/` layout (`src/shortlink_api/`), installed editable per `uv.lock` (`source = { editable = "." }`).
- **`config.py`**: a single `pydantic_settings.BaseSettings` (`Settings`), loaded once via `@lru_cache get_settings()`. Reads from a `.env` file resolved relative to the package (`parents[2] / ".env"`, i.e. repo root). All JWT-related fields are required with no defaults except algorithm/TTLs — the app will fail to start without `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_ISSUER`, `JWT_KEY_ID` set.
- **`core/security/`**: security primitives, independent of any web framework or DB.
  - `jwt.py` — ES256 JWT issuance/verification. `issue_token_pair()` produces an access+refresh pair in one call, both signed with the same private key, differentiated by a `type` claim (`TokenType.ACCESS`/`REFRESH`). `verify_token()` requires an `expected_type` and raises `InvalidTokenTypeError` if the token's `type` claim doesn't match — callers must not use one endpoint's verification for the other token type. Claims are validated into a `TokenClaims` pydantic model (`sub`, `iat`, `exp`, `jti`, `role`).
  - `password_hasher.py` — `PasswordHasher` ABC (`hash`, `matches`), decoupling the hashing algorithm from callers.
  - `bcrypt_password_hasher.py` — the bcrypt implementation. Passwords are SHA-256-prehashed (then base64-encoded) before being passed to bcrypt, to sidestep bcrypt's 72-byte input truncation. `matches()` swallows `ValueError`/`TypeError` from malformed input and returns `False` rather than raising.
- **`db/`**: `base.py` holds the declarative `Base` and the constraint/index naming convention (don't change it retroactively); `session.py` holds the async engine, `SessionLocal` and `get_db`. `config.py`'s `DB_URL` is a `sqlalchemy.engine.URL` (password-safe).
- **`models/`**: 2.0-style `User` and `Link` models. New models must be imported in `models/__init__.py` so Alembic autogenerate sees them.
- **`alembic/`**: async `env.py`; the URL comes from `config.py`, never `alembic.ini`. Autogenerate does not detect the `citext` extension or the `set_updated_at()` triggers — add those by hand in migrations (see 0001/0002). FK `links.user_id` is `ON DELETE SET NULL`.
- **`dependency.py`**: FastAPI dependency wiring, currently just `get_current_user`, which extracts a bearer token via `OAuth2PasswordBearer` and verifies it as an `ACCESS` token.
- **`api/`**: intended home for route modules (e.g. `auth.py`); not yet implemented.

## Design intent (from README.md — not yet built)

These are documented product/architecture decisions that should guide future implementation, even though the corresponding code doesn't exist yet:

- **Short codes**: generated from a Postgres sequence, base62-encoded, monotonic, never reused — Postgres (not Redis) is the source of truth so a cache loss can't cause collisions.
- **Redirects use 302**, never 301, so links stay editable/trackable (301 would get permanently cached by browsers/CDNs).
- **Cache-aside on Redis** in front of Postgres for redirects, with a 24h TTL that only expires the cache entry — links resolve indefinitely at the application level regardless of cache state. Key scheme is documented in the README's Redis table and `docs/db-schema.md`.
- **Click tracking is fire-and-forget** — never blocks the redirect response; counted via a background task.
- **Dedup is per-user** (`longurl:{user_id}:{hashed}`), not global — anonymous creates are never deduplicated. This is deliberate: a global dedup key would let unrelated users share a code, breaking single-owner mutation safety.
- **Anonymous link claiming**: `POST /links/{code}/claim` succeeds only if `owner_id IS NULL` (409 if already owned), and reactivates a soft-deleted link as a side effect.
- **Rate limiting**: fixed-window (Redis `INCR`+`EXPIRE`) on `POST /shorten` only; redirects are never rate-limited.
- **SSRF protection**: scheme allowlist (`http`/`https`) plus rejection of private/loopback/link-local/cloud-metadata target IPs, checked at creation time only (DNS rebinding at redirect time is an accepted limitation).
- **Purge pipeline** for cold links (90 days no clicks): soft-delete → 30-day grace period (410 Gone on redirect, owner can request reactivation) → archive to file → hard delete from Postgres. Hard delete is safe because codes are never reissued.
- **Auth**: JWT ES256, 15-min access / 7-day refresh TTLs (already reflected in `config.py` defaults and `core/security/jwt.py`).

See `docs/db-schema.md` for the full `users`/`links` table definitions, indexes (including the partial unique index on `code` for active links), and the purge-candidate query.
