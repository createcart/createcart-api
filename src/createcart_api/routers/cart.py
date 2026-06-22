"""Cart endpoints — HTTP layer over the Cart SDK, glued to the menu registry.

Shopper actions (add/inc/dec/remove/clear) are public but scoped to a cart id.
Prices are looked up authoritatively from the menu registry — the client never
sends a price. Charge/discount/tax changes require the admin key so shoppers
can't discount themselves.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from createcart_cart import Cart, CartItemNotFoundError, InvalidQuantityError
from createcart_registry import ItemNotFoundError, MenuRegistry

from ..deps import get_cart, get_registry, require_tenant_admin
from ..schemas import (
    AddToCart,
    ChargeIn,
    DiscountIn,
    QtyChange,
    SetQty,
    TaxIn,
)

router = APIRouter(prefix="/api/{tenant}/carts/{cart_id}", tags=["cart"])

admin = [Depends(require_tenant_admin)]


def _view(cart: Cart) -> dict:
    """Standard response: the full cart with per-line and grand totals."""
    return cart.to_dict()


def _missing(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── read ─────────────────────────────────────────────────────────────────
@router.get("")
def get_cart_view(cart: Cart = Depends(get_cart)) -> dict:
    return _view(cart)


# ── shopper item actions (public, scoped to cart id) ─────────────────────
@router.post("/items", status_code=status.HTTP_201_CREATED)
def add_to_cart(
    body: AddToCart,
    cart: Cart = Depends(get_cart),
    reg: MenuRegistry = Depends(get_registry),
) -> dict:
    # Look up the authoritative item — never trust a client-supplied price.
    try:
        item = reg.get_item(body.item_id)
    except ItemNotFoundError as exc:
        raise _missing(exc)
    if not item.in_stock:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{item.id!r} is not currently available",
        )
    try:
        cart.add_item(
            item.id,
            name=item.name,
            unit_price=item.price,
            quantity=body.quantity,
            icon=item.icon,
            image_url=item.image_url,
        )
    except InvalidQuantityError as exc:
        raise _bad(exc)
    return _view(cart)


@router.post("/items/{item_id}/increment")
def increment(
    item_id: str, body: QtyChange | None = None, cart: Cart = Depends(get_cart)
) -> dict:
    by = body.by if body else 1
    try:
        cart.increment(item_id, by)
    except CartItemNotFoundError as exc:
        raise _missing(exc)
    except InvalidQuantityError as exc:
        raise _bad(exc)
    return _view(cart)


@router.post("/items/{item_id}/decrement")
def decrement(
    item_id: str, body: QtyChange | None = None, cart: Cart = Depends(get_cart)
) -> dict:
    by = body.by if body else 1
    try:
        cart.decrement(item_id, by)
    except CartItemNotFoundError as exc:
        raise _missing(exc)
    except InvalidQuantityError as exc:
        raise _bad(exc)
    return _view(cart)


@router.put("/items/{item_id}")
def set_quantity(
    item_id: str, body: SetQty, cart: Cart = Depends(get_cart)
) -> dict:
    try:
        cart.set_quantity(item_id, body.quantity)
    except CartItemNotFoundError as exc:
        raise _missing(exc)
    return _view(cart)


@router.delete("/items/{item_id}")
def remove_item(item_id: str, cart: Cart = Depends(get_cart)) -> dict:
    try:
        cart.remove_item(item_id)
    except CartItemNotFoundError as exc:
        raise _missing(exc)
    return _view(cart)


@router.post("/clear")
def clear(cart: Cart = Depends(get_cart)) -> dict:
    cart.clear()
    return _view(cart)


# ── charge / discount / tax (admin only) ─────────────────────────────────
@router.post("/charges", dependencies=admin)
def set_charge(body: ChargeIn, cart: Cart = Depends(get_cart)) -> dict:
    cart.add_charge(body.code, body.label, body.amount)
    return _view(cart)


@router.delete("/charges/{code}", dependencies=admin)
def remove_charge(code: str, cart: Cart = Depends(get_cart)) -> dict:
    cart.remove_charge(code)
    return _view(cart)


@router.post("/discount", dependencies=admin)
def set_discount(body: DiscountIn, cart: Cart = Depends(get_cart)) -> dict:
    cart.set_discount(body.kind, body.value, code=body.code, label=body.label)
    return _view(cart)


@router.delete("/discount", dependencies=admin)
def clear_discount(cart: Cart = Depends(get_cart)) -> dict:
    cart.clear_discount()
    return _view(cart)


@router.post("/tax", dependencies=admin)
def set_tax(body: TaxIn, cart: Cart = Depends(get_cart)) -> dict:
    cart.set_tax_rate(body.percent)
    return _view(cart)
