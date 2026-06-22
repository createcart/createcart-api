"""Tenant admin auth — validate a client's tenant+password at login.

The client admin page calls ``GET /api/{tenant}/admin/me`` with its
``X-Tenant-Key`` (the tenant password). It returns 200 + identity when valid,
401 otherwise — so the page can gate access without ever asking for a base URL
or the platform key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from ..config import settings
from ..deps import _database, require_tenant_admin

router = APIRouter(prefix="/api/{tenant}", tags=["auth"])


@router.get("/admin/me", dependencies=[Depends(require_tenant_admin)])
def me(tenant: str = Path(...)) -> dict:
    out = {"tenant": tenant}
    if settings.storage == "sqlite":
        rec = _database().get_tenant(tenant)
        if rec:
            out["id"] = rec["id"]
            out["base_url"] = rec.get("base_url")
    return out
