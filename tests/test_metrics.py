from types import SimpleNamespace

import httpx

from ollama_prometheus_exporter.config import Settings
from ollama_prometheus_exporter.main import InferenceStatsCollector, _run_ollama_startup_check
from ollama_prometheus_exporter.metrics import InferenceStats


def test_inference_stats_from_payload_extracts_token_and_timing_fields() -> None:
    stats = InferenceStats.from_payload(
        "/api/generate",
        {
            "model": "llama3.2:latest",
            "done": True,
            "prompt_eval_count": 26,
            "eval_count": 25,
            "prompt_eval_duration": 24_513_279,
            "eval_duration": 87_765_742,
            "load_duration": 2_143_135_313,
            "total_duration": 2_267_458_140,
        },
    )

    assert stats is not None
    assert stats.model == "llama3.2:latest"
    assert stats.prompt_eval_count == 26
    assert stats.eval_count == 25
    assert stats.prompt_eval_duration_seconds == 0.024513279
    assert stats.eval_duration_seconds == 0.087765742
    assert stats.load_duration_seconds == 2.143135313
    assert stats.total_duration_seconds == 2.26745814


def test_inference_stats_collector_parses_streamed_ndjson_and_uses_final_chunk() -> None:
    collector = InferenceStatsCollector("/api/chat")

    collector.feed(b'{"model":"llama3.2:latest","message":{"role":"assistant","content":"He"}}\n')
    collector.feed(
        b'{"model":"llama3.2:latest","done":true,"prompt_eval_count":12,"eval_count":8,"prompt_eval_duration":100000000,"eval_duration":200000000,"load_duration":300000000,"total_duration":700000000}'
    )

    stats = collector.finalize()

    assert stats is not None
    assert stats.endpoint == "/api/chat"
    assert stats.model == "llama3.2:latest"
    assert stats.prompt_eval_count == 12
    assert stats.eval_count == 8
    assert stats.eval_duration_seconds == 0.2


def test_inference_stats_ignores_payloads_without_usage_fields() -> None:
    stats = InferenceStats.from_payload(
        "/api/generate",
        {"model": "llama3.2:latest", "done": True, "response": "hello"},
    )

    assert stats is None


class _FakeOllamaClient:
    def __init__(self, outcomes: list[Exception | None]) -> None:
        self._outcomes = outcomes
        self.calls: list[float] = []

    async def check_connection(self, *, timeout_seconds: float) -> None:
        self.calls.append(timeout_seconds)
        outcome = self._outcomes.pop(0)
        if outcome is not None:
            raise outcome


async def test_startup_check_marks_connection_good_after_success() -> None:
    client = _FakeOllamaClient([None])
    settings = Settings()
    state = SimpleNamespace(ollama_connection_ok=False)

    await _run_ollama_startup_check(client, settings, state)

    assert state.ollama_connection_ok is True
    assert client.calls == [5.0]


async def test_startup_check_retries_with_exponential_backoff(monkeypatch) -> None:
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("ollama_prometheus_exporter.main.asyncio.sleep", fake_sleep)

    client = _FakeOllamaClient(
        [
            httpx.ConnectError("boom"),
            httpx.ConnectError("boom"),
            None,
        ]
    )
    settings = Settings(ollama_startup_check_max_backoff_seconds=30.0)
    state = SimpleNamespace(ollama_connection_ok=False)

    await _run_ollama_startup_check(client, settings, state)

    assert state.ollama_connection_ok is True
    assert client.calls == [5.0, 5.0, 5.0]
    assert sleep_calls == [1.0, 2.0]
