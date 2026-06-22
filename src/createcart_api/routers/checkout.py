"""Checkout endpoints — turn a cart into a payment order and verify the payment.

Pricing is computed server-side from the cart (never trusting the client).
On a verified payment the cart is cleared. With the mock provider, the checkout
response includes a ready-to-verify payment pair so the whole flow works
locally without real Razorpay keys.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status

from createcart_auth import InvalidTokenError
from createcart_cart import Cart
from createcart_delivery import InvalidTransitionError
from createcart_payment import MockProvider, PaymentService, SignatureVerificationError

from ..config import settings
from ..deps import (
    _auth_service,
    cart_store_for,
    delivery_service_for,
    get_cart,
    get_payment_service,
)
from ..schemas import VerifyPayment

router = APIRouter(prefix="/api/{tenant}", tags=["checkout"])


def _to_minor(amount: Decimal) -> int:
    """Rupees (Decimal) -> paise (int)."""
    return int((amount * 100).to_integral_value())


@router.post("/carts/{cart_id}/checkout")
def checkout(
    tenant: str,
    cart_id: str,
    cart: Cart = Depends(get_cart),
    pay: PaymentService = Depends(get_payment_service),
) -> dict:
    if cart.is_empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cart is empty"
        )
    totals = cart.totals()
    amount_minor = _to_minor(totals.grand_total)
    order = pay.create_order(
        amount_minor,
        currency=totals.currency,
        receipt=f"{tenant}:{cart_id}",
        notes={"tenant": tenant, "cart_id": cart_id},
        cart_id=cart_id,
    )

    resp = {
        "provider": order.provider,
        "key_id": pay.public_key,
        "order_id": order.id,
        "amount": order.amount,          # paise
        "currency": order.currency,
        "name": settings.business_name,
        "grand_total": str(totals.grand_total),
    }
    # Local mock flow: hand back a valid pair so the frontend can simulate
    # a successful payment with no real gateway.
    if isinstance(pay.provider, MockProvider):
        resp["mock_payment"] = pay.provider.make_test_payment(order.id)
    return resp


@router.post("/payments/verify")
def verify_payment(
    tenant: str,
    body: VerifyPayment,
    pay: PaymentService = Depends(get_payment_service),
) -> dict:
    try:
        record = pay.verify_payment(body.order_id, body.payment_id, body.signature)
    except SignatureVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    # Tie the order to the signed-in user (verified server-side, not trusted
    # from the body) so it shows up in their order history.
    customer = body.customer.model_dump() if body.customer else {}
    if body.id_token:
        try:
            identity = _auth_service().verify(body.id_token)
            customer["subject"] = identity.subject
            customer["email"] = identity.email or customer.get("email")
            customer.setdefault("name", identity.name or "Customer")
        except InvalidTokenError:
            pass  # token optional — proceed without account linkage

    # Payment is good — create a delivery order from the cart snapshot, then
    # clear the cart.
    delivery_id = None
    if record.cart_id:
        cart = Cart(record.cart_id, store=cart_store_for(tenant))
        if not cart.is_empty:
            totals = cart.totals()
            items = [
                {
                    "item_id": i.item_id, "name": i.name,
                    "quantity": i.quantity, "unit_price": i.unit_price,
                }
                for i in cart.list_items()
            ]
            dsvc = delivery_service_for(tenant)
            try:
                d = dsvc.create_order(
                    id=record.order_id,         # tie delivery to the payment order
                    items=items,
                    customer=customer or None,
                    amount=totals.grand_total,
                    currency=totals.currency,
                    cart_id=record.cart_id,
                    payment_id=record.payment_id,
                )
                delivery_id = d.id
            except InvalidTransitionError:
                # already created (e.g. a duplicate verify call) — idempotent
                delivery_id = record.order_id
            cart.clear()

    return {
        "status": record.status.value,
        "order_id": record.order_id,
        "payment_id": record.payment_id,
        "amount": record.amount,
        "currency": record.currency,
        "delivery_order_id": delivery_id,
    }
