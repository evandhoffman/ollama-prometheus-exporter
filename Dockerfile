# syntax=docker/dockerfile:1

FROM cgr.dev/chainguard/python:latest-dev AS builder

WORKDIR /app

RUN python -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

COPY pyproject.toml README.md /app/
COPY src /app/src

RUN uv pip install --python /app/venv/bin/python /app

FROM cgr.dev/chainguard/python:latest

WORKDIR /app

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

COPY --from=builder /app/venv /app/venv
COPY --from=builder /app/src /app/src
COPY README.md /app/README.md

EXPOSE 9497

ENTRYPOINT ["/app/venv/bin/python", "-m", "ollama_prometheus_exporter.main"]
