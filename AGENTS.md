# AGENTS.md

## Project Overview

This repository contains an Ollama Prometheus exporter written in Python 3.13+.

The service acts as both:

- a Prometheus exporter on `/metrics`
- a reverse proxy for Ollama on `/api/*`

Token and timing metrics are collected from proxied inference responses, so clients must talk to the exporter rather than directly to Ollama if metrics are desired.

## Stack

- Python 3.13+
- `uv` for dependency management and execution
- FastAPI + Uvicorn
- `prometheus_client`
- Docker with Chainguard Python base images

## Local Commands

Install dev dependencies:

```bash
uv sync --extra dev
```

Run tests:

```bash
uv run --extra dev pytest
```

Run lint:

```bash
uv run --extra dev ruff check .
```

Run locally:

```bash
uv run ollama-prometheus-exporter
```

## Docker

Primary files:

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.deploy.yml`

Published image:

- `evandhoffman/ollama-prometheus-exporter:latest`

## GitHub Actions

This repo uses GitHub Actions for:

- CI test/lint
- Docker Hub image publishing
- Docker Hub README/description sync from `README.md`

Expected GitHub secrets:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

## Important Behavior

- The exporter performs an initial Ollama connectivity test at startup.
- It logs a clear success or failure message and retries with exponential backoff up to 30 seconds.
- `/` must support both `GET` and `HEAD` because the Ollama CLI probes it.
- `/health` may report `degraded` until the upstream Ollama connection succeeds.

## Editing Guidance

- Preserve the proxy behavior on `/api/*`.
- Preserve token/timing counters derived from Ollama inference responses.
- Prefer small, testable changes.
- Update `README.md` when changing deployment, metrics, configuration, or Docker behavior.
- Keep Docker Hub behavior aligned with existing automation in this repo.

## Git Workflow

Serialize git state-changing commands. Do not run these in parallel:

1. `git add`
2. `git commit`
3. `git push`

If a push depends on a newly created commit, always commit first and push second in separate steps.

## Verification Expectations

Before finishing code changes, run:

```bash
uv run --extra dev pytest
uv run --extra dev ruff check .
```

If a change affects container or release automation, mention whether GitHub Actions or Docker Hub behavior was verified.
