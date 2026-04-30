from __future__ import annotations

from typing import Protocol, runtime_checkable

Message = dict[str, str]


@runtime_checkable
class LLMClient(Protocol):
    provider: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str: ...


@runtime_checkable
class AsyncLLMClient(Protocol):
    provider: str
    model: str

    async def acomplete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str: ...
