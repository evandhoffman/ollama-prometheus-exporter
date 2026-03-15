"""Application entrypoint."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from . import __version__
from .client import OllamaClient
from .config import Settings, get_settings
from .metrics import (
    InferenceStats,
    RequestTimer,
    metrics_content_type,
    record_inference_stats,
    record_proxy_request,
    record_upstream_exception,
    render_metrics,
)

logger = logging.getLogger(__name__)

HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
INFERENCE_ENDPOINTS = {"/api/generate", "/api/chat"}


def configure_logging(settings: Settings) -> None:
    """Configure process logging."""

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create shared application state."""

    settings = get_settings()
    configure_logging(settings)
    app.state.settings = settings
    app.state.ollama_client = OllamaClient(settings)
    app.state.ollama_connection_ok = False
    app.state.ollama_startup_check_task = asyncio.create_task(
        _run_ollama_startup_check(app.state.ollama_client, settings, app.state)
    )
    yield
    app.state.ollama_startup_check_task.cancel()
    try:
        await app.state.ollama_startup_check_task
    except asyncio.CancelledError:
        pass
    await app.state.ollama_client.aclose()


app = FastAPI(
    title="Ollama Prometheus Exporter",
    description="Prometheus exporter and reverse proxy for Ollama metrics",
    version=__version__,
    lifespan=lifespan,
)


@app.get("/")
async def root() -> dict[str, object]:
    """Basic exporter metadata."""

    settings = get_settings()
    return {
        "name": "ollama-prometheus-exporter",
        "version": __version__,
        "mode": "proxy",
        "ollama_base_url": str(settings.ollama_base_url),
        "endpoints": {
            "/metrics": "prometheus",
            "/health": "exporter health",
            "/api/*": "proxied Ollama API",
        },
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Basic process health."""

    status = "ok" if app.state.ollama_connection_ok else "degraded"
    return {"status": status, "mode": "proxy"}


@app.get("/metrics")
async def metrics() -> Response:
    """Render Prometheus metrics."""

    return Response(content=render_metrics(), media_type=metrics_content_type())


@app.api_route(
    "/api/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def proxy_api(path: str, request: Request) -> Response:
    """Proxy an Ollama API request upstream."""

    endpoint = f"/api/{path}"
    timer = RequestTimer()
    content = await request.body()
    upstream_headers = _filter_request_headers(request.headers)
    upstream_request = request.app.state.ollama_client.build_request(
        method=request.method,
        path=endpoint,
        params=request.query_params,
        headers=upstream_headers,
        content=content or None,
    )

    try:
        upstream_response = await request.app.state.ollama_client.send(
            upstream_request,
            stream=endpoint in INFERENCE_ENDPOINTS,
        )
    except httpx.HTTPError as exc:
        logger.exception("Upstream Ollama request failed for %s", endpoint)
        record_upstream_exception(endpoint, request.method, exc.__class__.__name__, timer.elapsed())
        raise HTTPException(status_code=502, detail="Failed to reach upstream Ollama") from exc

    if endpoint in INFERENCE_ENDPOINTS:
        return await _proxy_inference_response(
            endpoint=endpoint,
            method=request.method,
            upstream_response=upstream_response,
            timer=timer,
        )

    body = await upstream_response.aread()
    await upstream_response.aclose()
    record_proxy_request(endpoint, request.method, upstream_response.status_code, timer.elapsed())
    return Response(
        content=body,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type"),
        headers=_filter_response_headers(upstream_response.headers),
    )


async def _proxy_inference_response(
    *,
    endpoint: str,
    method: str,
    upstream_response: httpx.Response,
    timer: RequestTimer,
) -> Response:
    """Proxy a streamed or buffered inference response and extract metrics."""

    stats_collector = InferenceStatsCollector(endpoint)
    response_headers = _filter_response_headers(upstream_response.headers)

    async def body_iterator() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream_response.aiter_bytes():
                stats_collector.feed(chunk)
                yield chunk
            stats = stats_collector.finalize()
            if stats is not None:
                record_inference_stats(stats)
        finally:
            record_proxy_request(endpoint, method, upstream_response.status_code, timer.elapsed())
            await upstream_response.aclose()

    return StreamingResponse(
        body_iterator(),
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type"),
        headers=response_headers,
    )


class InferenceStatsCollector:
    """Collect the last complete Ollama inference payload from streamed bytes."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint
        self._buffer = bytearray()
        self._last_payload: Mapping[str, Any] | None = None

    def feed(self, chunk: bytes) -> None:
        """Consume one body chunk."""

        if not chunk:
            return
        self._buffer.extend(chunk)
        self._consume_newline_delimited_json()

    def finalize(self) -> InferenceStats | None:
        """Finish parsing and convert the last payload into inference stats."""

        if self._buffer:
            remaining = bytes(self._buffer).strip()
            self._buffer.clear()
            if remaining:
                if b"\n" in remaining:
                    for line in remaining.splitlines():
                        self._consume_line(line)
                else:
                    self._consume_json_blob(remaining)
        if self._last_payload is None:
            return None
        return InferenceStats.from_payload(self._endpoint, self._last_payload)

    def _consume_newline_delimited_json(self) -> None:
        while True:
            newline_index = self._buffer.find(b"\n")
            if newline_index < 0:
                return
            line = bytes(self._buffer[:newline_index])
            del self._buffer[: newline_index + 1]
            self._consume_line(line)

    def _consume_line(self, line: bytes) -> None:
        line = line.strip()
        if line:
            self._consume_json_blob(line)

    def _consume_json_blob(self, blob: bytes) -> None:
        try:
            payload = json.loads(blob)
        except json.JSONDecodeError:
            return
        if isinstance(payload, dict):
            self._last_payload = payload


def _filter_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def _filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


async def _run_ollama_startup_check(
    ollama_client: OllamaClient,
    settings: Settings,
    state: Any,
) -> None:
    """Check Ollama connectivity until it succeeds."""

    backoff_seconds = 1.0
    logger.info("Doing initial ollama connection test...")

    while True:
        try:
            await ollama_client.check_connection(
                timeout_seconds=settings.ollama_startup_check_timeout_seconds
            )
            state.ollama_connection_ok = True
            logger.info("Connection to ollama server is good")
            return
        except httpx.HTTPError as exc:
            state.ollama_connection_ok = False
            logger.error(
                "Initial connection to ollama server failed: %s. Retrying in %.1f seconds",
                exc,
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            backoff_seconds = min(
                backoff_seconds * 2,
                settings.ollama_startup_check_max_backoff_seconds,
            )


def main() -> None:
    """Run the exporter."""

    settings = get_settings()
    configure_logging(settings)
    uvicorn.run(
        "ollama_prometheus_exporter.main:app",
        host=settings.exporter_host,
        port=settings.exporter_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
