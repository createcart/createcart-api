"""Delivery endpoints — track an order (public) and drive it (admin).

A delivery order is auto-created when a payment is verified (see checkout). The
customer can track it by id; the business advances its status through the
lifecycle with the admin key.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from createcart_delivery import (
    DeliveryNotFoundError,
    DeliveryService,
    InvalidTransitionError,
)

from ..deps import get_delivery_service, require_tenant_admin
from ..schemas import CancelBody, CourierIn, NoteBody, StatusChange

router = APIRouter(prefix="/api/{tenant}/deliveries", tags=["delivery"])

admin = [Depends(require_tenant_admin)]


def _missing(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ── customer: track ──────────────────────────────────────────────────────
@router.get("/{order_id}")
def track(order_id: str, svc: DeliveryService = Depends(get_delivery_service)) -> dict:
    try:
        return svc.track(order_id)
    except DeliveryNotFoundError as exc:
        raise _missing(exc)


# ── business: list + drive (admin) ───────────────────────────────────────
@router.get("", dependencies=admin)
def list_orders(
    status: Optional[str] = None,
    svc: DeliveryService = Depends(get_delivery_service),
) -> list[dict]:
    return [o.model_dump(mode="json") for o in svc.list(status=status)]


@router.post("/{order_id}/advance", dependencies=admin)
def advance(
    order_id: str,
    body: NoteBody | None = None,
    svc: DeliveryService = Depends(get_delivery_service),
) -> dict:
    try:
        return svc.advance(order_id, note=body.note if body else None).model_dump(mode="json")
    except DeliveryNotFoundError as exc:
        raise _missing(exc)
    except InvalidTransitionError as exc:
        raise _bad(exc)


@router.post("/{order_id}/status", dependencies=admin)
def set_status(
    order_id: str,
    body: StatusChange,
    svc: DeliveryService = Depends(get_delivery_service),
) -> dict:
    try:
        return svc.set_status(order_id, body.status, note=body.note).model_dump(mode="json")
    except DeliveryNotFoundError as exc:
        raise _missing(exc)
    except InvalidTransitionError as exc:
        raise _bad(exc)


@router.post("/{order_id}/cancel", dependencies=admin)
def cancel(
    order_id: str,
    body: CancelBody | None = None,
    svc: DeliveryService = Depends(get_delivery_service),
) -> dict:
    try:
        return svc.cancel(order_id, reason=body.reason if body else None).model_dump(mode="json")
    except DeliveryNotFoundError as exc:
        raise _missing(exc)
    except InvalidTransitionError as exc:
        raise _bad(exc)


@router.post("/{order_id}/courier", dependencies=admin)
def assign_courier(
    order_id: str,
    body: CourierIn,
    svc: DeliveryService = Depends(get_delivery_service),
) -> dict:
    try:
        return svc.assign_courier(
            order_id, body.name, phone=body.phone, tracking_url=body.tracking_url
        ).model_dump(mode="json")
    except DeliveryNotFoundError as exc:
        raise _missing(exc)
