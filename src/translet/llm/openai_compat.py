from __future__ import annotations

import os
from typing import Any

from .base import Message

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _require_openai() -> Any:
    try:
        import openai
    except ImportError as exc:
        raise ImportError(
            "translet's OpenAI-compatible LLM clients require the `openai` SDK. "
            "Install it via `pip install translet[openai]` (or [azure]/[groq]/[nvidia]/[all-llm])."
        ) from exc
    return openai


class OpenAICompatibleLLM:
    """Sync LLM client speaking the OpenAI Chat Completions protocol.

    Used directly for OpenAI, Groq, NVIDIA NIM, and any other endpoint exposing
    an OpenAI-compatible API. For Azure OpenAI, use :func:`azure` factory which
    constructs an `AzureOpenAI` client.
    """

    provider: str
    model: str

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ):
        self.provider = provider
        self.model = model
        if client is not None:
            self._client = client
        else:
            openai = _require_openai()
            self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


class AsyncOpenAICompatibleLLM:
    provider: str
    model: str

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
    ):
        self.provider = provider
        self.model = model
        if client is not None:
            self._client = client
        else:
            openai = _require_openai()
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def acomplete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


def openai(model: str, *, api_key: str | None = None, base_url: str | None = None) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        provider="openai",
        model=model,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
    )


def aopenai(model: str, *, api_key: str | None = None, base_url: str | None = None) -> AsyncOpenAICompatibleLLM:
    return AsyncOpenAICompatibleLLM(
        provider="openai",
        model=model,
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url,
    )


def groq(model: str, *, api_key: str | None = None) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        provider="groq",
        model=model,
        api_key=api_key or os.environ.get("GROQ_API_KEY"),
        base_url=_GROQ_BASE_URL,
    )


def agroq(model: str, *, api_key: str | None = None) -> AsyncOpenAICompatibleLLM:
    return AsyncOpenAICompatibleLLM(
        provider="groq",
        model=model,
        api_key=api_key or os.environ.get("GROQ_API_KEY"),
        base_url=_GROQ_BASE_URL,
    )


def nvidia(model: str, *, api_key: str | None = None) -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        provider="nvidia",
        model=model,
        api_key=api_key or os.environ.get("NVIDIA_API_KEY"),
        base_url=_NVIDIA_BASE_URL,
    )


def anvidia(model: str, *, api_key: str | None = None) -> AsyncOpenAICompatibleLLM:
    return AsyncOpenAICompatibleLLM(
        provider="nvidia",
        model=model,
        api_key=api_key or os.environ.get("NVIDIA_API_KEY"),
        base_url=_NVIDIA_BASE_URL,
    )


def azure(
    model: str,
    *,
    api_key: str | None = None,
    endpoint: str | None = None,
    api_version: str | None = None,
) -> OpenAICompatibleLLM:
    openai_mod = _require_openai()
    client = openai_mod.AzureOpenAI(
        api_key=api_key or os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_version=api_version or os.environ.get("AZURE_OPENAI_API_VERSION"),
    )
    return OpenAICompatibleLLM(provider="azure", model=model, client=client)


def aazure(
    model: str,
    *,
    api_key: str | None = None,
    endpoint: str | None = None,
    api_version: str | None = None,
) -> AsyncOpenAICompatibleLLM:
    openai_mod = _require_openai()
    client = openai_mod.AsyncAzureOpenAI(
        api_key=api_key or os.environ.get("AZURE_OPENAI_API_KEY"),
        azure_endpoint=endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT"),
        api_version=api_version or os.environ.get("AZURE_OPENAI_API_VERSION"),
    )
    return AsyncOpenAICompatibleLLM(provider="azure", model=model, client=client)
