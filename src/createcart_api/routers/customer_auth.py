"""Customer authentication — Sign in with Google (storefront shoppers).

Global (not tenant-scoped): a customer identity is the same person across stores.
`/api/auth/config` tells the frontend which provider + client id to use;
`/api/auth/google` verifies the login token and returns the user's identity.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from createcart_auth import AuthService, InvalidTokenError

from ..deps import _auth_service

router = APIRouter(prefix="/api/auth", tags=["customer-auth"])


class LoginBody(BaseModel):
    id_token: str


def get_auth() -> AuthService:
    return _auth_service()


@router.get("/config")
def auth_config(auth: AuthService = Depends(get_auth)) -> dict:
    """Public, non-secret config the storefront needs to render the login."""
    return auth.public_config


@router.post("/google")
def login_google(body: LoginBody, auth: AuthService = Depends(get_auth)) -> dict:
    """Verify a Google ID token (or mock token) and return the user identity."""
    try:
        identity = auth.verify(body.id_token)
    except InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))
    return identity.model_dump()
