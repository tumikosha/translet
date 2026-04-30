from __future__ import annotations

from typing import Any

from ._pipeline import AsyncDeps, SyncDeps, convert_async, convert_sync


class TransJson:
    """Sync facade for the JSON conversion pipeline."""

    def __init__(self, deps: SyncDeps):
        self._deps = deps

    def convert(
        self,
        source: Any,
        *,
        target_schema: Any = None,
        target_sample: Any = None,
        description: str | None = None,
        name: str | None = None,
    ) -> Any:
        return convert_sync(
            self._deps,
            source,
            target_schema=target_schema,
            target_sample=target_sample,
            description=description,
            name=name,
        )

    def invalidate(self, name_or_key: str) -> None:
        key = name_or_key if name_or_key.startswith(("name:", "hash:")) else f"name:{name_or_key}"
        self._deps.store.delete(key)

    def evict_expired(self, ttl_seconds: int | None = None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self._deps.config.ttl_seconds
        if ttl is None:
            return 0
        return self._deps.store.evict_expired(ttl)


class AsyncTransJson:
    """Async facade for the JSON conversion pipeline."""

    def __init__(self, deps: AsyncDeps):
        self._deps = deps

    async def aconvert(
        self,
        source: Any,
        *,
        target_schema: Any = None,
        target_sample: Any = None,
        description: str | None = None,
        name: str | None = None,
    ) -> Any:
        return await convert_async(
            self._deps,
            source,
            target_schema=target_schema,
            target_sample=target_sample,
            description=description,
            name=name,
        )

    async def ainvalidate(self, name_or_key: str) -> None:
        key = name_or_key if name_or_key.startswith(("name:", "hash:")) else f"name:{name_or_key}"
        await self._deps.store.adelete(key)

    async def aevict_expired(self, ttl_seconds: int | None = None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else self._deps.config.ttl_seconds
        if ttl is None:
            return 0
        return await self._deps.store.aevict_expired(ttl)
