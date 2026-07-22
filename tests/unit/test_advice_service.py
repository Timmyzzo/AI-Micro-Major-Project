"""Minimal aggregate-only API advice tests."""

from types import SimpleNamespace

from pydantic import SecretStr

from powerinsight.config import AppSettings
from powerinsight.services.advice_service import (
    AdviceSnapshot,
    generate_advice,
    probe_llm_connection,
)


class _Completions:
    def __init__(self, content: str | None = "建议内容") -> None:
        self.content = content
        self.calls: list[dict[str, object]] = []

    def create(self, **values: object) -> object:
        self.calls.append(values)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class _Client:
    def __init__(self, completions: _Completions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _settings() -> AppSettings:
    return AppSettings(
        llm_enabled=True,
        openai_api_key=SecretStr("secret"),
        openai_model="example-model",
    )


def test_generate_advice_uses_one_chat_completions_call_with_aggregate_json() -> None:
    completions = _Completions()
    snapshot = AdviceSnapshot(
        evidence={"average_power_kw": 1.2, "dataset_id": "ds_test"},
        template="本地模板",
    )

    result = generate_advice(snapshot, _settings(), client=_Client(completions))

    assert result.mode == "api"
    assert result.text == "建议内容"
    assert len(completions.calls) == 1
    messages = completions.calls[0]["messages"]
    assert "ds_test" in str(messages)
    assert "完整时序" not in str(messages)
    assert "约1000字" in str(messages)
    assert "现状判断" in str(messages)


def test_generate_advice_falls_back_when_response_is_empty() -> None:
    snapshot = AdviceSnapshot(evidence={}, template="本地模板")
    result = generate_advice(
        snapshot,
        _settings(),
        client=_Client(_Completions(content=None)),
    )

    assert result.mode == "template"
    assert result.text == "本地模板"
    assert result.diagnostic == "ValueError"


def test_generate_advice_keeps_a_long_model_response_complete() -> None:
    content = "这是一条具体可执行的用电管理建议。" * 80
    snapshot = AdviceSnapshot(evidence={}, template="本地模板")

    result = generate_advice(
        snapshot,
        _settings(),
        client=_Client(_Completions(content=content)),
    )

    assert result.mode == "api"
    assert result.text == content


def test_probe_llm_connection_sends_one_minimal_message() -> None:
    completions = _Completions(content="连接正常")

    result = probe_llm_connection(_settings(), client=_Client(completions))

    assert result.status == "success"
    assert result.model == "example-model"
    assert result.text == "连接正常"
    assert result.latency_ms is not None
    assert len(completions.calls) == 1
    assert completions.calls[0]["model"] == "example-model"
    assert "连接测试" in str(completions.calls[0]["messages"])


def test_probe_llm_connection_reports_incomplete_configuration() -> None:
    settings = AppSettings(
        llm_enabled=True,
        openai_api_key=None,
        openai_model=None,
    )

    result = probe_llm_connection(settings)

    assert result.status == "unconfigured"
    assert result.text is None
    assert result.diagnostic == "缺少API Key、模型"
