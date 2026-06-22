"""Customer order history — a signed-in shopper's own past orders.

Authenticated by the customer's Google token (header ``X-Auth-Token``); returns
only the orders whose verified ``subject`` matches the token. Lets the storefront
show "My Orders" with search + tracking, without exposing other customers' data.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Path, status

from createcart_auth import AuthService, InvalidTokenError
from createcart_delivery import DeliveryService

from ..deps import _auth_service, get_delivery_service

router = APIRouter(prefix="/api/{tenant}", tags=["customer-orders"])


def get_auth() -> AuthService:
    return _auth_service()


@router.get("/my-orders")
def my_orders(
    tenant: str = Path(...),
    x_auth_token: str = Header(default=""),
    svc: DeliveryService = Depends(get_delivery_service),
    auth: AuthService = Depends(get_auth),
) -> list[dict]:
    if not x_auth_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="missing X-Auth-Token")
    try:
        identity = auth.verify(x_auth_token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    orders = svc.list(subject=identity.subject)
    return [o.model_dump(mode="json") for o in orders]
