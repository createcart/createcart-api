# CreateCart — HTTP API

A **generic, multi-tenant** FastAPI service that exposes the
[CreateCart SDKs](https://github.com/createcart/createcart-sdks) (menu, cart,
payment, delivery, notify, auth) over HTTP so any tenant's JS frontend can
consume them. This is the "service" half of **Path B: Python SDKs as a service
API + themed JS frontends**.

The API itself is **tenant-agnostic** — every route is namespaced by tenant
(`/api/{tenant}/...`) and tenants are stored in a registry (numeric `id` `0..n`
↔ english `name`). *Brahmana Naivedyam* is just the first example tenant; it
lives entirely in runtime config (env vars) and the local `data/` dir, not in
the code.

```
JS frontend (per tenant)  ──HTTP──►  createcart-api  ──imports──►  createcart-sdks
   (own theme/UI)                    (this repo)                   (pure libraries)
                                          │
                                          └── storage: SQLite (per-tenant tables) or JSON files
```

## Install & run

The Python SDKs live in the separate `createcart-sdks` monorepo and are
installed alongside this service (no private registry needed yet):

```bash
# 1. runtime libs + the SDKs as editable local checkouts
pip install fastapi "uvicorn[standard]" "psycopg[binary]" pytest httpx
pip install -e ../createcart-sdks/packages/registry \
            -e ../createcart-sdks/packages/cart \
            -e ../createcart-sdks/packages/payment \
            -e ../createcart-sdks/packages/delivery \
            -e ../createcart-sdks/packages/notify \
            -e ../createcart-sdks/packages/auth \
            -e ../createcart-sdks/packages/store-sqlite \
            -e ../createcart-sdks/packages/store-postgres

# 2. install this API WITHOUT deps — its pyproject pins the SDKs to git (for the
#    Vercel build); --no-deps keeps your editable checkouts above instead.
pip install -e . --no-deps

# 3. run it
uvicorn createcart_api.main:app --reload          # http://127.0.0.1:8000
#    interactive docs:  http://127.0.0.1:8000/docs
```

> For a fully-configured local run (real Razorpay/Google keys, SQLite, notify),
> copy your secrets into a `run.ps1` and start with it. `run.ps1` is **git-ignored**
> — never commit real keys.

## Configuration (environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `CREATECART_STORAGE` | `sqlite` | `sqlite` (per-tenant tables in one DB), `postgres` (same schema on Postgres/Supabase), or `json` (per-tenant files) |
| `CREATECART_DB` | `data/createcart.db` | SQLite database path (when storage = sqlite) |
| `DATABASE_URL` | – | Postgres connection string (when storage = postgres). On Vercel use the Supabase **transaction pooler** URI (`:6543`) |
| `CREATECART_DATA_DIR` | `data` | Directory for JSON storage / seeds |
| `CREATECART_ADMIN_KEY` | `createcart-admin` | Platform-owner key for onboarding tenants (`X-Admin-Key`) |
| `CREATECART_CORS_ORIGINS` | `*` | Comma-separated allowed origins. Supports a `*` glob (`https://*.vercel.app`) and ignores trailing slashes. |
| `CREATECART_BUSINESS_NAME` | `CreateCart` | Display name (per deployment) |
| `CREATECART_PAYMENT_PROVIDER` | `mock` | `mock` or `razorpay` |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | – | Razorpay creds (secret stays server-side) |
| `CREATECART_AUTH_PROVIDER` | `google` if `GOOGLE_CLIENT_ID` set, else `mock` | Customer sign-in provider |
| `GOOGLE_CLIENT_ID` | – | Google OAuth client id (ID-token audience check) |
| `CREATECART_NOTIFY_ENABLED` | `1` | Send order-status follow-ups |
| `CREATECART_NOTIFY_PROVIDER` | `console` | `console` or `twilio` |
| `CREATECART_NOTIFY_CHANNEL` | `sms` | `sms` or `whatsapp` |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | – | Twilio creds (when provider = twilio) |
| `TWILIO_FROM_SMS` / `TWILIO_FROM_WHATSAPP` | – | Twilio sender numbers |

## Authentication (three tiers)

| Tier | Header | Used for |
|------|--------|----------|
| **Platform owner** | `X-Admin-Key: <admin key>` | Onboarding tenants, platform admin writes |
| **Tenant admin** | `X-Tenant-Key: <tenant password>` | Managing that tenant's own menu/orders (password is PBKDF2-hashed at rest; the platform `X-Admin-Key` also works) |
| **Customer** | `X-Auth-Token: <Google ID token>` | A signed-in customer's own data (e.g. `my-orders`); the token is verified against Google and the client-id audience |

## Endpoints

Public reads need no auth. Writes require the relevant tier above.

> **Always fresh, never cached.** Every response sends `Cache-Control: no-store`,
> and the menu registry is built **per request** (it reads the store each time)
> rather than cached in memory. On serverless this is what keeps a menu change
> saved by one instance (e.g. the admin app) instantly visible to reads served by
> any other (the website, the apps) — no stale snapshots.

**Platform — tenant registry** (`X-Admin-Key`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/_tenants` | List tenants |
| POST | `/api/_tenants` | Onboard a tenant `{ name, password?, base_url?, id? }` (idempotent upsert — also resets password / base_url) |
| GET | `/api/_tenants/{name}` | Get one tenant |
| DELETE | `/api/_tenants/{name}` | Off-board a tenant — deletes it and **drops all its tables** (irreversible) |

**Customer auth** (not tenant-scoped)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/auth/config` | Public auth config `{ provider, client_id? }` |
| POST | `/api/auth/google` | Verify a Google ID token → customer identity |

**Tenant admin login**
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/{tenant}/admin/me` | tenant | Validate tenant-admin credentials |

**Menu** (`/api/{tenant}`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/menu` · `/items` · `/items/{id}` · `/categories` · `/combos` | – | Read catalog (filters: `category`, `tag`, `available_only`, `in_stock_only`, `q`) |
| POST | `/items` | tenant | Create item |
| PATCH | `/items/{id}` | tenant | Update fields |
| DELETE | `/items/{id}` | tenant | Delete one item |
| DELETE | `/items` | tenant | Clear the whole menu (all items + combos; keeps categories) → `{ removed }` |
| POST | `/items/{id}/price` · `/availability` · `/stock/set` · `/stock/adjust` | tenant | Pricing / availability / stock |
| POST | `/categories` · `/combos` | tenant | Create category / combo |

**Cart** (`/api/{tenant}/carts/{cart_id}`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `` | Get cart + totals |
| POST | `/items` | Add line |
| POST | `/items/{id}/increment` · `/decrement` | Change quantity |
| PUT / DELETE | `/items/{id}` | Set quantity / remove line |
| POST | `/clear` | Empty cart |
| POST / DELETE | `/charges` · `/charges/{code}` | Add / remove a charge |
| POST / DELETE | `/discount` | Set / clear discount |
| POST | `/tax` | Set tax rate |

**Checkout** (`/api/{tenant}`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/carts/{cart_id}/checkout` | Price the cart server-side, create a payment order |
| POST | `/payments/verify` | Verify payment (signature), clear cart, create delivery order; optional `id_token` attaches the customer |

**Delivery** (`/api/{tenant}/deliveries`, mutations = tenant admin)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{order_id}` | Track one order (status + timeline) — public |
| GET | `` | List orders (tenant) |
| POST | `/{order_id}/advance` · `/status` · `/cancel` · `/courier` | Drive the lifecycle (tenant) |

**Customer orders** (`/api/{tenant}`)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/my-orders` | customer | The signed-in customer's past orders |

## Storage

- **`sqlite`** (default) — one database, **separate tables per tenant**
  (`menu_items_<id>`, `carts_<id>`, `payments_<id>`, `deliveries_<id>`, …) plus a
  `tenants` registry. Backed by the `createcart-store-sqlite` SDK.
- **`postgres`** — the **same per-tenant schema** on Postgres/Supabase. Set
  `CREATECART_STORAGE=postgres` and `DATABASE_URL`. Backed by the
  `createcart-store-postgres` SDK.
- **`json`** — per-tenant JSON files under `CREATECART_DATA_DIR`. Backed by each
  SDK's `JSONFile*Store`.

All three implement the same SDK storage protocols, so switching backends is a
config change — no code changes.

## Deploy (Vercel + Supabase)

This repo is Vercel-ready: `api/index.py` exposes the ASGI `app`, `vercel.json`
rewrites every route to it, and **Vercel builds from `pyproject.toml` with `uv`**
(it installs the SDKs from the public monorepo; `[tool.hatch.metadata]
allow-direct-references = true` lets the git deps build).

1. **Supabase** → create a project; copy the **transaction pooler** URI (`:6543`)
   for `DATABASE_URL`, and the **session pooler** URI (`:5432`) for the one-time
   migration. URL-encode the password (`@`→`%40`); append `?sslmode=require`.
2. **Vercel** → import this repo; set env vars (`CREATECART_STORAGE=postgres`,
   `DATABASE_URL=<transaction-pooler URI>`, `CREATECART_ADMIN_KEY`, payment/auth keys,
   `CREATECART_CORS_ORIGINS=https://<your-storefront>`). Deploy; check `/health`.
3. **Migrate existing data** into Supabase (use the **session** pooler, port 5432):
   ```bash
   pip install -e ../createcart-sdks/packages/store-postgres   # local only
   python scripts/migrate_sqlite_to_postgres.py data/createcart.db \
     "host=aws-0-<region>.pooler.supabase.com port=5432 dbname=postgres user=postgres.<ref> password=<pw> sslmode=require"
   ```

The per-operation connection model suits serverless behind the Supabase pooler
(prepared statements are disabled in `store-postgres` for pgbouncer compatibility).

> **Important:** use the Supabase **pooler** host (IPv4), not the direct
> `db.<ref>.supabase.co` host (IPv6 — unreachable from Vercel). The pooler region in
> the host must match your project. A fuller troubleshooting table lives in the
> repo-root `README.md` (§13).

## Onboarding a tenant

```bash
curl -X POST http://localhost:8000/api/_tenants \
  -H "X-Admin-Key: $CREATECART_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"brahmana-naivedyam","password":"<tenant-pw>","base_url":"http://localhost:8000"}'
```

The tenant's frontend then uses `X-Tenant-Key: <tenant-pw>` for admin actions and
public routes for the storefront.

## Test

```bash
pip install -e ".[dev]"   # SDKs must be installed too (see Install)
pytest -q
```

## Related repos

- **[createcart-sdks](https://github.com/createcart/createcart-sdks)** — the pure
  headless libraries this service imports.
- Each tenant's website — imports the `js-client` SDK and brings its own theme.
