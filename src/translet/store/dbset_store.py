from __future__ import annotations

from datetime import timedelta
from typing import Any

from .base import Rule, _utcnow

DEFAULT_TABLE = "translet_rules"


def _is_missing_column_error(exc: Exception) -> bool:
    """dbset raises QueryError when querying a column on a freshly-created (empty) table.

    We treat that as "no such row" rather than propagating, so callers can probe an
    empty store without first inserting.
    """
    return type(exc).__name__ == "QueryError" and "not found in table" in str(exc)


class DbSetStore:
    """Sync rule storage backed by a dbset connection.

    The caller owns the dbset connection lifecycle. Pass any object that exposes
    dict-style access to a table with the standard dbset methods
    (``insert``, ``upsert``, ``find``, ``find_one``, ``update``, ``delete``).
    """

    def __init__(self, db: Any, *, table: str = DEFAULT_TABLE):
        self._db = db
        self._table_name = table

    @property
    def _table(self) -> Any:
        return self._db[self._table_name]

    def get(self, key: str) -> Rule | None:
        try:
            row = self._table.find_one(key=key)
        except Exception as exc:
            if _is_missing_column_error(exc):
                return None
            raise
        if row is None:
            return None
        return Rule.from_row(dict(row))

    def put(self, rule: Rule) -> None:
        self._table.upsert(rule.to_row(), keys=["key"])

    def touch(self, key: str, *, success: bool) -> None:
        rule = self.get(key)
        if rule is None:
            return
        rule.use_count += 1
        if success:
            rule.success_count += 1
        else:
            rule.failure_count += 1
        rule.last_used_at = _utcnow()
        self.put(rule)

    def delete(self, key: str) -> None:
        try:
            self._table.delete(key=key)
        except Exception as exc:
            if not _is_missing_column_error(exc):
                raise

    def evict_expired(self, ttl_seconds: int) -> int:
        cutoff = (_utcnow() - timedelta(seconds=ttl_seconds)).isoformat()
        try:
            expired = list(self._table.find(last_used_at={"<": cutoff}))
        except Exception as exc:
            if _is_missing_column_error(exc):
                return 0
            raise
        for row in expired:
            self._table.delete(key=row["key"])
        return len(expired)

    def list(self, *, limit: int = 100) -> list[Rule]:
        try:
            rows = list(self._table.find())
        except Exception as exc:
            if _is_missing_column_error(exc):
                return []
            raise
        return [Rule.from_row(dict(r)) for r in rows[:limit]]


class AsyncDbSetStore:
    """Async counterpart of :class:`DbSetStore`."""

    def __init__(self, db: Any, *, table: str = DEFAULT_TABLE):
        self._db = db
        self._table_name = table

    @property
    def _table(self) -> Any:
        return self._db[self._table_name]

    async def aget(self, key: str) -> Rule | None:
        try:
            row = await self._table.find_one(key=key)
        except Exception as exc:
            if _is_missing_column_error(exc):
                return None
            raise
        if row is None:
            return None
        return Rule.from_row(dict(row))

    async def aput(self, rule: Rule) -> None:
        await self._table.upsert(rule.to_row(), keys=["key"])

    async def atouch(self, key: str, *, success: bool) -> None:
        rule = await self.aget(key)
        if rule is None:
            return
        rule.use_count += 1
        if success:
            rule.success_count += 1
        else:
            rule.failure_count += 1
        rule.last_used_at = _utcnow()
        await self.aput(rule)

    async def adelete(self, key: str) -> None:
        try:
            await self._table.delete(key=key)
        except Exception as exc:
            if not _is_missing_column_error(exc):
                raise

    async def aevict_expired(self, ttl_seconds: int) -> int:
        cutoff = (_utcnow() - timedelta(seconds=ttl_seconds)).isoformat()
        expired: list[dict] = []
        try:
            async for row in self._table.find(last_used_at={"<": cutoff}):
                expired.append(dict(row))
        except Exception as exc:
            if _is_missing_column_error(exc):
                return 0
            raise
        for row in expired:
            await self._table.delete(key=row["key"])
        return len(expired)

    async def alist(self, *, limit: int = 100) -> list[Rule]:
        rules: list[Rule] = []
        try:
            async for row in self._table.find():
                rules.append(Rule.from_row(dict(row)))
                if len(rules) >= limit:
                    break
        except Exception as exc:
            if _is_missing_column_error(exc):
                return []
            raise
        return rules
