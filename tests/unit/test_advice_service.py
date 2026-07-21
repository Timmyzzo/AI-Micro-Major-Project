"""Minimal aggregate-only API advice tests."""

from types import SimpleNamespace

from pydantic import SecretStr

from powerinsight.config import AppSettings
from powerinsight.services.advice_service import AdviceSnapshot, generate_advice


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
