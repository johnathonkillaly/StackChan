from __future__ import annotations

from typing import Any

import httpx


class HomeAssistantAdapter:
    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.enabled = enabled
        self.base_url = base_url.rstrip("/") if base_url else None
        self.token = token
        self.timeout_seconds = timeout_seconds
        self._transport = transport

    async def trigger_service(self, domain: str, service: str, data: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled or not self.base_url or not self.token:
            return {
                "status": "disabled",
                "message": "Home Assistant adapter is disabled or missing config.",
                "domain": domain,
                "service": service,
            }

        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=self.timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(f"/api/services/{domain}/{service}", json=data)
            response.raise_for_status()
            return {
                "status": "ok",
                "domain": domain,
                "service": service,
                "response": response.json(),
            }

