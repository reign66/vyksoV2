"""
Authentication Utilities
========================
Supabase JWT validation shared by all routes.

Extracted from main.py so that routes (checkout, etc.) and main.py can use
the same helper. Behavior is identical to main.py's _get_authenticated_user_id:
- Reads `Authorization: Bearer <jwt>` from the request
- Validates the JWT against `{SUPABASE_URL}/auth/v1/user`
- Returns the Supabase user id
- Raises HTTPException(401) on missing/invalid token
"""

import os
import httpx
from fastapi import HTTPException, Request

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_OR_SERVICE_KEY = (
    os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_SERVICE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)


async def get_authenticated_user_id(request: Request) -> str:
    """Validate Supabase JWT from Authorization header and return user id (sub).

    This calls Supabase Auth `/auth/v1/user` which verifies the Bearer JWT.
    Requires SUPABASE_URL and an API key (anon or service) in env.

    Raises:
        HTTPException(401): missing/invalid/expired token
        HTTPException(500): Supabase auth not configured
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    jwt_token = auth_header[len("Bearer "):].strip()

    if not SUPABASE_URL or not SUPABASE_ANON_OR_SERVICE_KEY:
        raise HTTPException(status_code=500, detail="Supabase auth not configured")

    auth_user_url = f"{SUPABASE_URL}/auth/v1/user"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            auth_user_url,
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "apikey": SUPABASE_ANON_OR_SERVICE_KEY,
            },
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        data = resp.json()
        user_id = data.get("id") or data.get("sub")
    except Exception:
        user_id = None
    if not user_id:
        raise HTTPException(status_code=401, detail="Unable to resolve user from token")
    return user_id
