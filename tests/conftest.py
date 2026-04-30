from __future__ import annotations

import pytest

from translet.llm import Message
from translet.store import AsyncRuleStore, Rule, RuleStore


class FakeLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses) if responses else []
        self.calls: list[list[Message]] = []

    def queue(self, *responses: str) -> None:
        self.responses.extend(responses)

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("FakeLLM: no responses queued")
        return self.responses.pop(0)


class FakeAsyncLLM:
    provider = "fake"
    model = "fake-1"

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses) if responses else []
        self.calls: list[list[Message]] = []

    def queue(self, *responses: str) -> None:
        self.responses.extend(responses)

    async def acomplete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("FakeAsyncLLM: no responses queued")
        return self.responses.pop(0)


class InMemoryStore(RuleStore):
    def __init__(self) -> None:
        self._rows: dict[str, Rule] = {}

    def get(self, key: str) -> Rule | None:
        rule = self._rows.get(key)
        if rule is None:
            return None
        return _copy_rule(rule)

    def put(self, rule: Rule) -> None:
        self._rows[rule.key] = _copy_rule(rule)

    def touch(self, key: str, *, success: bool) -> None:
        rule = self._rows.get(key)
        if rule is None:
            return
        rule.use_count += 1
        if success:
            rule.success_count += 1
        else:
            rule.failure_count += 1

    def delete(self, key: str) -> None:
        self._rows.pop(key, None)

    def evict_expired(self, ttl_seconds: int) -> int:
        return 0

    def list(self, *, limit: int = 100) -> list[Rule]:
        return [_copy_rule(r) for r in list(self._rows.values())[:limit]]


class InMemoryAsyncStore(AsyncRuleStore):
    def __init__(self) -> None:
        self._sync = InMemoryStore()

    async def aget(self, key: str) -> Rule | None:
        return self._sync.get(key)

    async def aput(self, rule: Rule) -> None:
        self._sync.put(rule)

    async def atouch(self, key: str, *, success: bool) -> None:
        self._sync.touch(key, success=success)

    async def adelete(self, key: str) -> None:
        self._sync.delete(key)

    async def aevict_expired(self, ttl_seconds: int) -> int:
        return self._sync.evict_expired(ttl_seconds)

    async def alist(self, *, limit: int = 100) -> list[Rule]:
        return self._sync.list(limit=limit)


def _copy_rule(rule: Rule) -> Rule:
    return Rule(
        key=rule.key,
        jsonata_rule=rule.jsonata_rule,
        source_shape=dict(rule.source_shape) if isinstance(rule.source_shape, dict) else rule.source_shape,
        target_kind=rule.target_kind,
        target_spec=rule.target_spec,
        provider=rule.provider,
        model=rule.model,
        version=rule.version,
        use_count=rule.use_count,
        success_count=rule.success_count,
        failure_count=rule.failure_count,
        created_at=rule.created_at,
        last_used_at=rule.last_used_at,
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def fake_async_llm() -> FakeAsyncLLM:
    return FakeAsyncLLM()


@pytest.fixture
def memory_store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def memory_async_store() -> InMemoryAsyncStore:
    return InMemoryAsyncStore()
