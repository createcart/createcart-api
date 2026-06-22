"""FastAPI dependencies: per-tenant registry access and admin auth."""

from __future__ import annotations

from functools import lru_cache

from fastapi import Header, HTTPException, Path, status

from createcart_auth import AuthService, GoogleProvider
from createcart_auth import MockProvider as AuthMockProvider
from createcart_cart import Cart
from createcart_cart.storage import JSONFileCartStore
from createcart_delivery import DeliveryService
from createcart_delivery.storage import JSONFileDeliveryStore
from createcart_notify import ConsoleProvider, NotifyService, TwilioProvider
from createcart_payment import MockProvider, PaymentService, RazorpayProvider
from createcart_payment.storage import JSONFilePaymentStore
from createcart_registry import MenuRegistry
from createcart_registry.storage import JSONFileStore
from createcart_store_sqlite import (
    Database,
    SqliteCartStore,
    SqliteDeliveryStore,
    SqliteMenuStore,
    SqlitePaymentStore,
)

from .config import settings

TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{1,62}$"
CART_ID_PATTERN = r"^[A-Za-z0-9_-]{1,128}$"


@lru_cache(maxsize=1)
def _database():
    """One shared tenant-registry DB handle for the process.

    Postgres/Supabase when ``CREATECART_STORAGE=postgres`` (lazy import so a
    SQLite-only dev install needs no psycopg), else SQLite.
    """
    if settings.storage == "postgres":
        from createcart_store_postgres import PgDatabase

        return PgDatabase(settings.database_url)
    return Database(settings.db_path)


def _menu_store(tenant: str):
    if settings.storage == "postgres":
        from createcart_store_postgres import PgMenuStore

        return PgMenuStore(_database(), tenant)
    if settings.storage == "sqlite":
        return SqliteMenuStore(_database(), tenant)
    return JSONFileStore(settings.data_dir / f"{tenant}.json")


def _cart_store(tenant: str):
    if settings.storage == "postgres":
        from createcart_store_postgres import PgCartStore

        return PgCartStore(_database(), tenant)
    if settings.storage == "sqlite":
        return SqliteCartStore(_database(), tenant)
    return JSONFileCartStore(settings.data_dir / "carts" / tenant)


def _payment_store(tenant: str):
    if settings.storage == "postgres":
        from createcart_store_postgres import PgPaymentStore

        return PgPaymentStore(_database(), tenant)
    if settings.storage == "sqlite":
        return SqlitePaymentStore(_database(), tenant)
    return JSONFilePaymentStore(settings.data_dir / "payments" / tenant)


def _delivery_store(tenant: str):
    if settings.storage == "postgres":
        from createcart_store_postgres import PgDeliveryStore

        return PgDeliveryStore(_database(), tenant)
    if settings.storage == "sqlite":
        return SqliteDeliveryStore(_database(), tenant)
    return JSONFileDeliveryStore(settings.data_dir / "deliveries" / tenant)


@lru_cache(maxsize=1)
def _auth_service() -> AuthService:
    """Build the configured customer-identity service once for the process."""
    if settings.auth_provider == "google":
        return AuthService(GoogleProvider(settings.google_client_id))
    return AuthService(AuthMockProvider())


@lru_cache(maxsize=1)
def _notify_service() -> NotifyService:
    """Build the configured notification service once for the process."""
    if settings.notify_provider == "twilio":
        provider = TwilioProvider(
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            from_sms=settings.twilio_from_sms or None,
            from_whatsapp=settings.twilio_from_whatsapp or None,
        )
    else:
        provider = ConsoleProvider()
    return NotifyService(provider, business_name=settings.business_name)


def _notify_on_event(order, event) -> None:
    """Delivery on_event hook: text the customer's phone on every status change.

    Defensive — a notification failure must never break the order operation.
    """
    if not settings.notify_enabled:
        return
    customer = order.customer
    if not customer or not customer.phone:
        return
    try:
        _notify_service().notify_status(
            customer.phone, order.status.value,
            name=customer.name, order_id=order.id, channel=settings.notify_channel,
        )
    except Exception:  # pragma: no cover - never let notifications break orders
        pass


def delivery_service_for(tenant: str) -> DeliveryService:
    """Delivery service for a tenant (used by the delivery router and at checkout).

    Wired with the notify hook so each status change follows up to the phone.
    """
    return DeliveryService(_delivery_store(tenant), on_event=_notify_on_event)


def get_delivery_service(
    tenant: str = Path(..., pattern=TENANT_PATTERN),
) -> DeliveryService:
    return delivery_service_for(tenant)


@lru_cache(maxsize=None)
def _registry_for(tenant: str) -> MenuRegistry:
    """One cached MenuRegistry per tenant, backed by the configured store."""
    return MenuRegistry(store=_menu_store(tenant), tenant=tenant)


def get_registry(tenant: str = Path(..., pattern=TENANT_PATTERN)) -> MenuRegistry:
    """Resolve the registry for the ``{tenant}`` path segment.

    The pattern keeps tenant ids slug-safe so they can't escape the data dir.
    """
    return _registry_for(tenant)


def get_cart(
    tenant: str = Path(..., pattern=TENANT_PATTERN),
    cart_id: str = Path(..., pattern=CART_ID_PATTERN),
) -> Cart:
    """Resolve a shopper's cart, persisted at <data_dir>/carts/<tenant>/<cart_id>.json.

    Carts aren't cached: each request loads fresh from disk so concurrent
    shoppers never share in-memory state.
    """
    return Cart(cart_id, store=_cart_store(tenant))


@lru_cache(maxsize=1)
def _payment_provider():
    """Build the configured payment provider once for the process."""
    if settings.payment_provider == "razorpay":
        return RazorpayProvider(settings.razorpay_key_id, settings.razorpay_key_secret)
    return MockProvider()


def get_payment_service(tenant: str = Path(..., pattern=TENANT_PATTERN)) -> PaymentService:
    """Payment service for a tenant, recording orders via the configured store."""
    return PaymentService(_payment_provider(), store=_payment_store(tenant))


def cart_store_for(tenant: str):
    """The cart store for a tenant (used to clear a cart after payment)."""
    return _cart_store(tenant)


def require_admin(x_admin_key: str = Header(default="")) -> None:
    """Platform-owner guard — the global admin key (``X-Admin-Key``).

    Used for onboarding tenants. Also acts as a superuser for tenant endpoints.
    """
    if x_admin_key != settings.admin_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing X-Admin-Key",
        )


def require_tenant_admin(
    tenant: str = Path(..., pattern=TENANT_PATTERN),
    x_admin_key: str = Header(default=""),
    x_tenant_key: str = Header(default=""),
) -> None:
    """Guard a tenant's own admin actions.

    Allows EITHER the platform admin key (superuser) OR the tenant's own
    password (``X-Tenant-Key``), verified against the stored hash.
    """
    from .security import verify_password

    if x_admin_key and x_admin_key == settings.admin_key:
        return  # platform superuser
    if settings.uses_db:
        record = _database().get_tenant(tenant)
        if record and verify_password(x_tenant_key, record.get("password_hash")):
            return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing tenant credentials (X-Tenant-Key)",
    )
