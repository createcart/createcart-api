"""Request body schemas for the API.

Responses reuse the SDK's own pydantic models (MenuItem, Category, Combo),
so there's a single source of truth for menu shapes.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    name: str
    price: Decimal | float | int | str = 0
    id: Optional[str] = None
    name_localized: Optional[str] = None
    description: str = ""
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    icon: Optional[str] = None
    image_url: Optional[str] = None
    available: bool = True
    stock: Optional[int] = None
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ItemUpdate(BaseModel):
    """All fields optional — only those sent are applied (PATCH semantics)."""

    name: Optional[str] = None
    price: Decimal | float | int | str | None = None
    name_localized: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    available: Optional[bool] = None
    stock: Optional[int] = None
    sort_order: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class PriceUpdate(BaseModel):
    price: Decimal | float | int | str


class AvailabilityUpdate(BaseModel):
    available: bool


class StockAdjust(BaseModel):
    delta: int


class StockSet(BaseModel):
    stock: Optional[int] = None


class CategoryCreate(BaseModel):
    name: str
    id: Optional[str] = None
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ComboCreate(BaseModel):
    name: str
    price: Decimal | float | int | str = 0
    id: Optional[str] = None
    description: str = ""
    item_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    available: bool = True
    sort_order: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── cart bodies ───────────────────────────────────────────────────────────
class AddToCart(BaseModel):
    item_id: str
    quantity: int = 1


class QtyChange(BaseModel):
    by: int = 1


class SetQty(BaseModel):
    quantity: int


class ChargeIn(BaseModel):
    code: str
    label: str
    amount: Decimal | float | int | str


class DiscountIn(BaseModel):
    kind: Literal["percent", "fixed"]
    value: Decimal | float | int | str
    code: Optional[str] = None
    label: Optional[str] = None


class TaxIn(BaseModel):
    percent: Decimal | float | int | str


# ── checkout / payment bodies ─────────────────────────────────────────────
class CustomerIn(BaseModel):
    name: str
    phone: Optional[str] = None
    address: Optional[str] = None
    email: Optional[str] = None
    lat: Optional[float] = None      # delivery location (geolocation)
    lng: Optional[float] = None


class VerifyPayment(BaseModel):
    order_id: str
    payment_id: str
    signature: str
    customer: Optional[CustomerIn] = None   # for the delivery order created on success
    id_token: Optional[str] = None          # signed-in user's token → ties order to account


# ── delivery bodies ───────────────────────────────────────────────────────
class StatusChange(BaseModel):
    status: Literal[
        "placed", "confirmed", "preparing", "out_for_delivery", "delivered", "cancelled"
    ]
    note: Optional[str] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


class CancelBody(BaseModel):
    reason: Optional[str] = None


class CourierIn(BaseModel):
    name: str
    phone: Optional[str] = None
    tracking_url: Optional[str] = None


# ── tenant admin bodies ───────────────────────────────────────────────────
class TenantCreate(BaseModel):
    name: str
    password: Optional[str] = None      # the client admin's login password
    base_url: Optional[str] = None      # stored; baked into the client page
    id: Optional[int] = None            # optional explicit tenant id
