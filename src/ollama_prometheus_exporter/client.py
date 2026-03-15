"""Async client wrapper for Ollama's HTTP API."""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from .config import Settings


class OllamaClient:
    """Shared HTTP client for Ollama proxying."""

    def __init__(self, settings: Settings) -> None:
        self._client = httpx.AsyncClient(
            base_url=str(settings.ollama_base_url),
            timeout=settings.ollama_timeout_seconds,
            verify=settings.ollama_verify_tls,
        )

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""

        await self._client.aclose()

    def build_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Request:
        """Build an upstream request."""

        return self._client.build_request(
            method=method,
            url=path,
            params=params,
            headers=headers,
            content=content,
        )

    async def send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        """Send a pre-built upstream request."""

        return await self._client.send(request, stream=stream)
