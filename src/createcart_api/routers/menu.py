"""Menu endpoints — thin HTTP layer over the MenuRegistry SDK.

Reads are public; writes require the admin key (see ``require_admin``).
The SDK raises typed errors which we map to HTTP status codes.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from createcart_registry import (
    Category,
    Combo,
    DuplicateItemError,
    ItemNotFoundError,
    MenuItem,
    MenuRegistry,
    OutOfStockError,
)

from ..deps import get_registry, require_tenant_admin
from ..schemas import (
    AvailabilityUpdate,
    CategoryCreate,
    ComboCreate,
    ItemCreate,
    ItemUpdate,
    PriceUpdate,
    StockAdjust,
    StockSet,
)

router = APIRouter(prefix="/api/{tenant}", tags=["menu"])

# Writes share one dependency list — the tenant's own admin (or platform key).
admin = [Depends(require_tenant_admin)]


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _conflict(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# ── reads (public) ───────────────────────────────────────────────────────
@router.get("/menu")
def get_menu(reg: MenuRegistry = Depends(get_registry)) -> dict:
    """The full catalog (items + categories + combos) as JSON."""
    return reg.to_dict()


@router.get("/items", response_model=list[MenuItem])
def list_items(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    available_only: bool = False,
    in_stock_only: bool = False,
    q: Optional[str] = None,
    reg: MenuRegistry = Depends(get_registry),
) -> list[MenuItem]:
    if q:
        return reg.search(q)
    return reg.list_items(
        category=category,
        tag=tag,
        available_only=available_only,
        in_stock_only=in_stock_only,
    )


@router.get("/items/{item_id}", response_model=MenuItem)
def get_item(item_id: str, reg: MenuRegistry = Depends(get_registry)) -> MenuItem:
    try:
        return reg.get_item(item_id)
    except ItemNotFoundError as exc:
        raise _not_found(exc)


@router.get("/categories", response_model=list[Category])
def list_categories(reg: MenuRegistry = Depends(get_registry)) -> list[Category]:
    return reg.list_categories()


@router.get("/combos", response_model=list[Combo])
def list_combos(
    available_only: bool = False, reg: MenuRegistry = Depends(get_registry)
) -> list[Combo]:
    return reg.list_combos(available_only=available_only)


# ── item writes (admin) ──────────────────────────────────────────────────
@router.post(
    "/items", response_model=MenuItem, status_code=status.HTTP_201_CREATED,
    dependencies=admin,
)
def create_item(
    body: ItemCreate, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    try:
        return reg.add_item(**body.model_dump())
    except DuplicateItemError as exc:
        raise _conflict(exc)


@router.patch("/items/{item_id}", response_model=MenuItem, dependencies=admin)
def update_item(
    item_id: str, body: ItemUpdate, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    fields = body.model_dump(exclude_unset=True)
    try:
        return reg.update_item(item_id, **fields)
    except ItemNotFoundError as exc:
        raise _not_found(exc)


@router.delete(
    "/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=admin
)
def delete_item(item_id: str, reg: MenuRegistry = Depends(get_registry)) -> None:
    try:
        reg.remove_item(item_id)
    except ItemNotFoundError as exc:
        raise _not_found(exc)


@router.post("/items/{item_id}/price", response_model=MenuItem, dependencies=admin)
def set_price(
    item_id: str, body: PriceUpdate, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    try:
        return reg.set_price(item_id, body.price)
    except ItemNotFoundError as exc:
        raise _not_found(exc)


@router.post(
    "/items/{item_id}/availability", response_model=MenuItem, dependencies=admin
)
def set_availability(
    item_id: str, body: AvailabilityUpdate, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    try:
        return reg.set_available(item_id, body.available)
    except ItemNotFoundError as exc:
        raise _not_found(exc)


@router.post("/items/{item_id}/stock/set", response_model=MenuItem, dependencies=admin)
def set_stock(
    item_id: str, body: StockSet, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    try:
        return reg.set_stock(item_id, body.stock)
    except ItemNotFoundError as exc:
        raise _not_found(exc)
    except OutOfStockError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/items/{item_id}/stock/adjust", response_model=MenuItem, dependencies=admin
)
def adjust_stock(
    item_id: str, body: StockAdjust, reg: MenuRegistry = Depends(get_registry)
) -> MenuItem:
    try:
        return reg.adjust_stock(item_id, body.delta)
    except ItemNotFoundError as exc:
        raise _not_found(exc)
    except OutOfStockError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── category / combo writes (admin) ──────────────────────────────────────
@router.post(
    "/categories", response_model=Category, status_code=status.HTTP_201_CREATED,
    dependencies=admin,
)
def create_category(
    body: CategoryCreate, reg: MenuRegistry = Depends(get_registry)
) -> Category:
    try:
        return reg.add_category(**body.model_dump())
    except DuplicateItemError as exc:
        raise _conflict(exc)


@router.post(
    "/combos", response_model=Combo, status_code=status.HTTP_201_CREATED,
    dependencies=admin,
)
def create_combo(body: ComboCreate, reg: MenuRegistry = Depends(get_registry)) -> Combo:
    try:
        return reg.add_combo(**body.model_dump())
    except DuplicateItemError as exc:
        raise _conflict(exc)
    except ItemNotFoundError as exc:
        raise _not_found(exc)
