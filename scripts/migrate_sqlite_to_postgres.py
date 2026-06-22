"""Copy tenants + menu (+ delivery orders) from the local SQLite DB into Postgres.

Run this ONCE to move your existing data into Supabase. Use the Supabase
**direct** connection string (port 5432) for the destination — not the pooler.

    python scripts/migrate_sqlite_to_postgres.py \
        data/createcart.db \
        "postgresql://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require"

Copies, per tenant:
  - the registry row (id, name, password_hash, base_url) — ids are preserved
  - the full menu catalog (items, categories, combos)
  - delivery orders (so existing order tracking keeps working)

Idempotent: re-running overwrites the menu and tenant fields. Carts (transient)
and raw payment records are not copied.
"""

from __future__ import annotations

import sys

from createcart_store_sqlite import Database, SqliteMenuStore, SqliteDeliveryStore
from createcart_store_postgres import PgDatabase, PgMenuStore, PgDeliveryStore


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    sqlite_path, dsn = sys.argv[1], sys.argv[2]

    src = Database(sqlite_path)
    dst = PgDatabase(dsn)

    tenants = src.list_tenants()  # [(id, name), ...]
    if not tenants:
        print(f"No tenants found in {sqlite_path}.")
        return

    for tid, name in tenants:
        rec = src.get_tenant(name) or {}
        # Preserve the tenant id and auth fields.
        dst.get_or_create_tenant(name, tenant_id=tid)
        dst.update_tenant(
            name,
            password_hash=rec.get("password_hash"),
            base_url=rec.get("base_url"),
        )
        # Menu catalog.
        catalog = SqliteMenuStore(src, name).load()
        PgMenuStore(dst, name).save(catalog)
        # Delivery orders (best effort).
        orders = SqliteDeliveryStore(src, name).list()
        pg_del = PgDeliveryStore(dst, name)
        for order in orders:
            pg_del.save(order)
        print(
            f"  tenant {tid} '{name}': "
            f"{len(catalog.items)} items, {len(catalog.categories)} categories, "
            f"{len(catalog.combos)} combos, {len(orders)} orders"
        )

    print(f"Done — migrated {len(tenants)} tenant(s) into Postgres.")


if __name__ == "__main__":
    main()
