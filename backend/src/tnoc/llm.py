from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from tnoc.settings import Settings

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class PromptRegistry:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._cache: dict[str, str] = {}

    def get(self, name: str) -> str:
        if name not in self._cache:
            path = self._directory / f"{name}.md"
            self._cache[name] = path.read_text(encoding="utf-8").strip()
        return self._cache[name]


def build_chat_model(settings: Settings) -> BaseChatModel:
    provider = settings.llm_provider.casefold().replace("-", "_")
    if provider == "openai":
        if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value():
            raise ValueError("OPENAI_API_KEY required when LLM_PROVIDER=openai")
        return ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key.get_secret_value(),
            use_responses_api=True,
            reasoning={"effort": settings.llm_reasoning_effort, "summary": "auto"},
            store=settings.openai_store,
            timeout=settings.model_timeout_seconds,
            max_retries=0,
        )
    if provider in {"gemini", "google", "google_genai"}:
        key = next(
            (
                secret.get_secret_value()
                for secret in (settings.google_api_key, settings.gemini_api_key)
                if secret is not None and secret.get_secret_value()
            ),
            None,
        )
        if key is None:
            raise ValueError(
                "GOOGLE_API_KEY or GEMINI_API_KEY required when LLM_PROVIDER=google_genai"
            )
        return ChatGoogleGenerativeAI(
            model=settings.llm_model,
            api_key=key,
            request_timeout=settings.model_timeout_seconds,
            retries=0,
        )
    return init_chat_model(
        model=settings.llm_model,
        model_provider=settings.llm_provider,
    )
