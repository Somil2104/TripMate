import os
import time
from typing import Any, Dict, Optional

import httpx


class AmadeusClient:
    """
    Thin async wrapper around Amadeus Self-Service APIs.

    - Handles OAuth2 client_credentials
    - Caches the access token in memory until it expires
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        # Root URL (no /v1 or /v2 suffix)
        self.base_url = base_url or os.getenv(
            "AMADEUS_BASE_URL", "https://test.api.amadeus.com"
        )
        try:
            self.client_id = os.environ["AMADEUS_CLIENT_ID"]
            self.client_secret = os.environ["AMADEUS_CLIENT_SECRET"]
        except KeyError as exc:
            raise RuntimeError(
                "Missing AMADEUS_CLIENT_ID or AMADEUS_CLIENT_SECRET env vars"
            ) from exc

        self._access_token: Optional[str] = None
        self._token_expiry: float = 0.0

        # One async client reused for all calls
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _authenticate(self) -> None:
        """
        Get a fresh access token from Amadeus and update internal cache.
        """
        token_url = "/v1/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        resp = await self._http.post(token_url, data=data, headers=headers)
        resp.raise_for_status()
        payload: Dict[str, Any] = resp.json()

        self._access_token = payload["access_token"]
        # expires_in is in seconds
        expires_in = int(payload.get("expires_in", 1800))
        # Refresh 1 minute before expiry
        self._token_expiry = time.time() + expires_in - 60

    async def _get_access_token(self) -> str:
        if not self._access_token or time.time() >= self._token_expiry:
            await self._authenticate()
        assert self._access_token is not None
        return self._access_token

    async def get(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform an authenticated GET to the given path (starting with /v1 or /v2).
        """
        token = await self._get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        resp = await self._http.get(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()
