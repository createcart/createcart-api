"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


class Settings:
    """Process-wide settings. Override via env vars."""

    def __init__(self) -> None:
        # Where data is persisted.
        self.data_dir = Path(os.environ.get("CREATECART_DATA_DIR", "data"))
        # Storage backend: "sqlite" (per-tenant tables in one DB) or "json".
        self.storage = os.environ.get("CREATECART_STORAGE", "sqlite")
        # SQLite database path (used when storage == "sqlite").
        self.db_path = os.environ.get(
            "CREATECART_DB", str(self.data_dir / "createcart.db")
        )
        # Key required on all mutating (admin) endpoints.
        self.admin_key = os.environ.get("CREATECART_ADMIN_KEY", "createcart-admin")
        # Comma-separated allowed CORS origins ("*" for any during dev).
        self.cors_origins = [
            o.strip()
            for o in os.environ.get("CREATECART_CORS_ORIGINS", "*").split(",")
            if o.strip()
        ]
        # Payments: "mock" (local, no keys) or "razorpay".
        self.payment_provider = os.environ.get("CREATECART_PAYMENT_PROVIDER", "mock")
        self.razorpay_key_id = os.environ.get("RAZORPAY_KEY_ID", "")
        self.razorpay_key_secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
        # Shown on the checkout widget.
        self.business_name = os.environ.get("CREATECART_BUSINESS_NAME", "CreateCart")
        # Notifications: provider "console" (local) or "twilio"; channel sms|whatsapp.
        self.notify_enabled = os.environ.get("CREATECART_NOTIFY_ENABLED", "1") not in (
            "0", "false", "False", "",
        )
        self.notify_provider = os.environ.get("CREATECART_NOTIFY_PROVIDER", "console")
        self.notify_channel = os.environ.get("CREATECART_NOTIFY_CHANNEL", "sms")
        self.twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.twilio_from_sms = os.environ.get("TWILIO_FROM_SMS", "")
        self.twilio_from_whatsapp = os.environ.get("TWILIO_FROM_WHATSAPP", "")
        # Customer auth: "google" (Sign in with Google) or "mock" (local, no project).
        # Defaults to google when a client id is configured, else mock.
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.auth_provider = os.environ.get(
            "CREATECART_AUTH_PROVIDER", "google" if self.google_client_id else "mock"
        )


settings = Settings()
