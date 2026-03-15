from ollama_prometheus_exporter.main import InferenceStatsCollector
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
