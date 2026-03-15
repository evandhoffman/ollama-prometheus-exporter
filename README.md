# Ollama Prometheus Exporter

Prometheus exporter and reverse proxy for an [Ollama](https://ollama.com/) service, typically running at `http://localhost:11434`.

The exporter exposes:

- `GET /metrics` for Prometheus scraping
- `GET /health` for a basic health check
- `GET /` for exporter metadata
- `ALL /api/*` as a reverse proxy to the upstream Ollama API

## How It Works

This exporter is meant to sit in front of Ollama.

- Your applications send Ollama requests to the exporter instead of directly to Ollama.
- The exporter forwards those requests to the upstream Ollama instance.
- When Ollama returns a completed inference response, the exporter extracts token and timing fields and turns them into Prometheus counters.

This is necessary because token counts are only exposed by inference responses such as `/api/generate` and `/api/chat`, not by passive endpoints like `/api/tags`.

## Starting It

### Local with `uv`

Requirements:

- Python 3.13 or newer
- `uv`

Install dependencies:

```bash
uv sync --extra dev
```

Start the exporter:

```bash
export OLLAMA_BASE_URL=http://localhost:11434
uv run ollama-prometheus-exporter
```

The exporter will listen on `http://0.0.0.0:9497` by default.

### Docker

Build the image:

```bash
docker build -t ollama-prometheus-exporter .
```

Run it:

```bash
docker run --rm -p 9497:9497 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  ollama-prometheus-exporter
```

### Docker Compose

An example `docker-compose.yml` is included:

```bash
docker compose up --build -d
```

If Ollama is running on the Docker host:

- On macOS and Windows, `host.docker.internal` usually works.
- On Linux, replace it with the host IP or add an `extra_hosts` mapping.

## Metrics

The exporter currently provides these Prometheus metrics:

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `ollama_proxy_requests_total` | Counter | `endpoint`, `method`, `status_code` | Total proxied Ollama API requests |
| `ollama_proxy_request_duration_seconds` | Histogram | `endpoint`, `method` | End-to-end proxy request latency |
| `ollama_proxy_upstream_exceptions_total` | Counter | `endpoint`, `method`, `error_type` | Upstream proxy failures |
| `ollama_inference_requests_total` | Counter | `endpoint`, `model` | Completed inference requests observed by the proxy |
| `ollama_prompt_tokens_total` | Counter | `endpoint`, `model` | Prompt tokens processed by Ollama |
| `ollama_generated_tokens_total` | Counter | `endpoint`, `model` | Generated output tokens |
| `ollama_prompt_eval_seconds_total` | Counter | `endpoint`, `model` | Prompt token evaluation time in seconds |
| `ollama_eval_seconds_total` | Counter | `endpoint`, `model` | Output token generation time in seconds |
| `ollama_load_seconds_total` | Counter | `endpoint`, `model` | Model load time reported by Ollama |
| `ollama_inference_seconds_total` | Counter | `endpoint`, `model` | Total inference duration reported by Ollama |

Metrics are currently extracted from completed responses on:

- `/api/generate`
- `/api/chat`

Prometheus can then derive decode throughput, for example:

```promql
rate(ollama_generated_tokens_total[5m]) / rate(ollama_eval_seconds_total[5m])
```

And raw generated token rate:

```promql
rate(ollama_generated_tokens_total[5m])
```

## Configuration

The exporter reads configuration from environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Upstream Ollama API base URL |
| `EXPORTER_HOST` | `0.0.0.0` | Bind address for the exporter |
| `EXPORTER_PORT` | `9497` | Exporter port |
| `OLLAMA_TIMEOUT_SECONDS` | `5.0` | Per-request Ollama timeout |
| `OLLAMA_VERIFY_TLS` | `true` | Enable TLS certificate verification |
| `LOG_LEVEL` | `INFO` | Logging level |

Example:

```bash
export OLLAMA_BASE_URL=http://192.168.1.110:11434
export EXPORTER_PORT=9497
export LOG_LEVEL=INFO
uv run ollama-prometheus-exporter
```

## Endpoints

| Endpoint | Purpose |
| --- | --- |
| `/` | Basic exporter metadata |
| `/health` | Process health |
| `/metrics` | Prometheus scrape target |
| `/api/*` | Reverse proxy to upstream Ollama |

## Using the Proxy

Point your Ollama clients at the exporter instead of directly at Ollama.

For example, if the exporter runs on `http://localhost:9497`, send requests to:

- `http://localhost:9497/api/generate`
- `http://localhost:9497/api/chat`
- `http://localhost:9497/api/tags`

Those requests will be forwarded to `OLLAMA_BASE_URL`.

## Configuring Clients To Use The Proxy

The key rule is simple:

- Keep `OLLAMA_BASE_URL` pointed at the real Ollama server.
- Point your clients at the exporter instead of the real Ollama server.

Example topology:

- Real Ollama: `http://192.168.1.110:11434`
- Exporter/proxy: `http://192.168.1.120:9497`

In that setup:

- Set `OLLAMA_BASE_URL=http://192.168.1.110:11434` on the exporter
- Configure clients to use `http://192.168.1.120:9497`

### Ollama Clients

Any client or tool that supports a custom Ollama base URL should be pointed at the exporter.

Use:

```text
http://YOUR_EXPORTER_HOST:9497
```

Instead of:

```text
http://YOUR_OLLAMA_HOST:11434
```

Examples:

- Old direct URL: `http://192.168.1.110:11434`
- New proxied URL: `http://192.168.1.120:9497`

### OpenClaw

If OpenClaw has an Ollama base URL or provider endpoint setting, set that value to the exporter URL instead of the upstream Ollama URL.

Use:

```text
http://YOUR_EXPORTER_HOST:9497
```

Do not use:

```text
http://YOUR_OLLAMA_HOST:11434
```

If OpenClaw is running in Docker Compose alongside this exporter, point OpenClaw at the exporter service name on the Compose network. For example:

```text
http://ollama-prometheus-exporter:9497
```

### Docker Compose Example

If another service in the same Compose project should use this proxy, configure that service to talk to `http://ollama-prometheus-exporter:9497`.

Example:

```yaml
services:
  openclaw:
    environment:
      OLLAMA_BASE_URL: http://ollama-prometheus-exporter:9497

  ollama-prometheus-exporter:
    build:
      context: .
    environment:
      OLLAMA_BASE_URL: http://host.docker.internal:11434
```

### Important Caveat

Token metrics are only captured for requests that actually pass through the proxy.

If some clients continue talking directly to Ollama at `:11434`, those requests will not appear in:

- `ollama_prompt_tokens_total`
- `ollama_generated_tokens_total`
- `ollama_eval_seconds_total`

## Local Development

This project targets Python 3.13+ and uses `uv`.

```bash
uv sync --extra dev
uv run ollama-prometheus-exporter
```

Run tests:

```bash
uv run --extra dev pytest
```

Lint:

```bash
uv run --extra dev ruff check .
```
