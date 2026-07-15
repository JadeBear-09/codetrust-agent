from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from codetrust.llm import GEMINI_BASE_URL, SynthesisError, _limit_words, model_status, synthesize


def test_gemini_configuration_uses_compatible_endpoint(monkeypatch) -> None:
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"intent":"Verify scope","summary":"No drift","unresolved_questions":[]}'
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODETRUST_MODEL", raising=False)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeClient))

    result = synthesize("# Ticket", "", [], offline=False)

    assert captured["client"] == {
        "api_key": "test-key",
        "base_url": GEMINI_BASE_URL,
        "timeout": 30.0,
        "max_retries": 0,
    }
    assert captured["request"]["model"] == "gemini-3.5-flash"
    assert captured["request"]["reasoning_effort"] == "low"
    assert result.model == "gemini-3.5-flash"
    assert result.status == "complete"
    assert result.attempts == 1


def test_offline_mode_never_calls_provider(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **kwargs: (_ for _ in ()).throw(AssertionError())),
    )

    result = synthesize("# Ticket", "", [], offline=True)

    assert result.model is None
    assert result.status == "disabled"


def test_model_status_exposes_metadata_not_secret(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    monkeypatch.setenv("CODETRUST_MODEL", "gemini-custom")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    status = model_status()

    assert status == {
        "configured": True,
        "provider": "gemini",
        "model": "gemini-custom",
    }
    assert "super-secret" not in str(status)


def test_gemini_transient_error_uses_fallback_model(monkeypatch) -> None:
    requested_models = []

    class TransientError(Exception):
        status_code = 503

    class FakeCompletions:
        def create(self, **kwargs):
            requested_models.append(kwargs["model"])
            if len(requested_models) == 1:
                raise TransientError("provider busy")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content='{"intent":"Verify scope","summary":"Fallback worked","unresolved_questions":[]}'
                        )
                    )
                ]
            )

    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CODETRUST_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("CODETRUST_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeClient))

    result = synthesize("# Ticket", "", [], offline=False)

    assert requested_models == ["gemini-3.5-flash", "gemini-3.1-flash-lite"]
    assert result.model == "gemini-3.1-flash-lite"


def test_required_model_timeout_fails_after_bounded_attempts(monkeypatch) -> None:
    requested_models = []

    class APITimeoutError(Exception):
        pass

    class FakeCompletions:
        def create(self, **kwargs):
            requested_models.append(kwargs["model"])
            raise APITimeoutError("timed out")

    class FakeClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CODETRUST_MODEL", "gemini-3.5-flash")
    monkeypatch.setenv("CODETRUST_FALLBACK_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("CODETRUST_MODEL_MAX_ATTEMPTS", "3")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeClient))

    with pytest.raises(SynthesisError) as caught:
        synthesize("# Ticket", "", [], offline=False)

    assert caught.value.code == "MODEL_TIMEOUT"
    assert caught.value.attempts == 3
    assert requested_models == [
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite",
    ]


def test_model_prose_is_bounded_even_if_provider_ignores_prompt() -> None:
    shortened = _limit_words("one two three four five", 3)

    assert shortened == "one two three…"
