"""Platform-level tenant admin endpoints (admin-key protected).

Manages the tenant registry: list tenants and their ids, register a new tenant,
or look one up. Lives at ``/api/_tenants`` (the leading underscore can't collide
with the slug pattern used for ``/api/{tenant}/...`` routes).

In SQLite mode this is backed by the ``tenants`` table (id 0..n ↔ name). In JSON
mode it derives tenants from the data directory.
"""

from __future__ import annotations

import glob
import os
import re

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import settings
from ..deps import _database, require_admin
from ..schemas import TenantCreate

router = APIRouter(
    prefix="/api/_tenants", tags=["tenants"], dependencies=[Depends(require_admin)]
)

_SLUG = re.compile(r"^[a-z][a-z0-9-]{0,62}$")


def _json_tenants() -> list[dict]:
    """Derive tenants from <data_dir>/<tenant>.json files (JSON mode)."""
    out = []
    for i, path in enumerate(sorted(glob.glob(str(settings.data_dir / "*.json")))):
        name = os.path.splitext(os.path.basename(path))[0]
        out.append({"id": i, "name": name})
    return out


@router.get("")
def list_tenants() -> list[dict]:
    if settings.storage == "sqlite":
        return _database().list_tenants_full()   # id, name, base_url (no password)
    return _json_tenants()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tenant(body: TenantCreate) -> dict:
    """Onboard a tenant: assign id, set the client's password + base URL."""
    from ..security import hash_password

    name = body.name.strip()
    if settings.storage == "sqlite":
        db = _database()
        try:
            tid = db.get_or_create_tenant(name, tenant_id=body.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        db.update_tenant(
            name,
            password_hash=hash_password(body.password) if body.password else None,
            base_url=body.base_url,
        )
        return {"id": tid, "name": name, "base_url": body.base_url,
                "has_password": bool(body.password)}
    if not _SLUG.match(name):
        raise HTTPException(status_code=400, detail="invalid tenant name")
    return {"id": None, "name": name, "base_url": body.base_url}


@router.get("/{name}")
def get_tenant(name: str) -> dict:
    if settings.storage == "sqlite":
        rec = _database().get_tenant(name)
        if rec is None:
            raise HTTPException(status_code=404, detail=f"no tenant named {name!r}")
        return {"id": rec["id"], "name": rec["name"], "base_url": rec.get("base_url"),
                "has_password": bool(rec.get("password_hash"))}
    if any(t["name"] == name for t in _json_tenants()):
        return {"id": None, "name": name}
    raise HTTPException(status_code=404, detail=f"no tenant named {name!r}")
