from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

TargetKind = Literal["schema", "sample", "description"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Rule:
    key: str
    jsonata_rule: str
    source_shape: dict
    target_kind: TargetKind
    target_spec: Any
    provider: str
    model: str
    version: int = 1
    use_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: datetime = field(default_factory=_utcnow)
    last_used_at: datetime = field(default_factory=_utcnow)

    def to_row(self) -> dict:
        row = asdict(self)
        row["created_at"] = self.created_at.isoformat()
        row["last_used_at"] = self.last_used_at.isoformat()
        if isinstance(self.target_spec, dict):
            row["target_spec_json"] = self.target_spec
            row["target_spec_text"] = None
        else:
            row["target_spec_json"] = None
            row["target_spec_text"] = str(self.target_spec)
        del row["target_spec"]
        return row

    @classmethod
    def from_row(cls, row: dict) -> Rule:
        target_spec: Any
        if row.get("target_spec_json") is not None:
            target_spec = row["target_spec_json"]
        else:
            target_spec = row.get("target_spec_text")
        return cls(
            key=row["key"],
            jsonata_rule=row["jsonata_rule"],
            source_shape=row["source_shape"],
            target_kind=row["target_kind"],
            target_spec=target_spec,
            provider=row["provider"],
            model=row["model"],
            version=int(row.get("version", 1)),
            use_count=int(row.get("use_count", 0)),
            success_count=int(row.get("success_count", 0)),
            failure_count=int(row.get("failure_count", 0)),
            created_at=_parse_dt(row["created_at"]),
            last_used_at=_parse_dt(row["last_used_at"]),
        )


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value))


@runtime_checkable
class RuleStore(Protocol):
    def get(self, key: str) -> Rule | None: ...
    def put(self, rule: Rule) -> None: ...
    def touch(self, key: str, *, success: bool) -> None: ...
    def delete(self, key: str) -> None: ...
    def evict_expired(self, ttl_seconds: int) -> int: ...
    def list(self, *, limit: int = 100) -> list[Rule]: ...


@runtime_checkable
class AsyncRuleStore(Protocol):
    async def aget(self, key: str) -> Rule | None: ...
    async def aput(self, rule: Rule) -> None: ...
    async def atouch(self, key: str, *, success: bool) -> None: ...
    async def adelete(self, key: str) -> None: ...
    async def aevict_expired(self, ttl_seconds: int) -> int: ...
    async def alist(self, *, limit: int = 100) -> list[Rule]: ...
