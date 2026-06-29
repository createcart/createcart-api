"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import (
    auth,
    cart,
    checkout,
    customer_auth,
    customer_orders,
    delivery,
    menu,
    tenants,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="CreateCart API",
        version="0.1.0",
        description="Serves the CreateCart menu registry to JS frontends.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _no_store(request, call_next):
        """Never let a browser or proxy serve cached API data.

        Everything here is dynamic (menus change, carts/orders are live), so a
        stale cached response would show wrong info. ``setdefault`` lets any
        endpoint opt into its own caching later if needed.
        """
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    app.include_router(tenants.router)
    app.include_router(auth.router)
    app.include_router(customer_auth.router)
    app.include_router(menu.router)
    app.include_router(cart.router)
    app.include_router(checkout.router)
    app.include_router(delivery.router)
    app.include_router(customer_orders.router)
    return app


app = create_app()
