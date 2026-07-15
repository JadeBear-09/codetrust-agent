from __future__ import annotations

import sys
from types import SimpleNamespace

from codetrust.llm import GEMINI_BASE_URL, model_status, synthesize


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
        "timeout": 20.0,
        "max_retries": 2,
    }
    assert captured["request"]["model"] == "gemini-3.5-flash"
    assert result.model == "gemini-3.5-flash"


def test_offline_mode_never_calls_provider(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=lambda **kwargs: (_ for _ in ()).throw(AssertionError())),
    )

    result = synthesize("# Ticket", "", [], offline=True)

    assert result.model is None


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
