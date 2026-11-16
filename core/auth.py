"""API key -> Principal. Shared by api/ and memory/router.py.

Identity comes ONLY from the X-API-Key header, mapped by DEMO_PRINCIPALS in .env. Nothing in a
request body, a log, a memory or something spoken to the voice agent can change who is calling.
These are demo keys, not real authentication: say so in the README.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from contracts.models import Principal
from core.config import get_settings


def get_principal(x_api_key: Annotated[str | None, Header()] = None) -> Principal:
    if not x_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-API-Key header.")
    entry = get_settings().demo_principals.get(x_api_key)
    if entry is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown API key.")
    return Principal.model_validate(entry)


def require_admin(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.role != "memory_admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a memory admin can do this.")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
AdminPrincipal = Annotated[Principal, Depends(require_admin)]
