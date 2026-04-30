from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from ..exceptions import ConversionError, JsonataError, ValidationError
from ..llm import AsyncLLMClient, LLMClient
from ..store import (
    AsyncRuleStore,
    Rule,
    RuleStore,
    TargetKind,
)
from ..store.base import _utcnow
from .key_builder import build_key, shape
from .rule_generator import (
    AsyncRuleGenerator,
    ErrorContext,
    GenerationContext,
    PromptBuilder,
    RuleGenerator,
)
from .runner import JsonataRunner
from .validator import ResultValidator


@dataclass(slots=True)
class PipelineConfig:
    max_retries: int = 2
    on_failure: str = "regenerate"
    validate: bool = True
    ttl_seconds: int | None = None
    temperature: float = 0.0
    max_tokens: int = 2048
    sample_truncate_bytes: int = 2048


def _resolve_target(
    target_schema: Any,
    target_sample: Any,
    description: str | None,
) -> tuple[TargetKind, Any]:
    provided = sum(x is not None for x in (target_schema, target_sample, description))
    if provided != 1:
        raise ValueError(
            "Exactly one of target_schema, target_sample, or description must be provided."
        )
    if target_schema is not None:
        return "schema", target_schema
    if target_sample is not None:
        return "sample", target_sample
    return "description", description


def _is_expired(rule: Rule, ttl_seconds: int | None) -> bool:
    if ttl_seconds is None:
        return False
    return _utcnow() - rule.last_used_at > timedelta(seconds=ttl_seconds)


@dataclass(slots=True)
class SyncDeps:
    llm: LLMClient
    store: RuleStore
    config: PipelineConfig
    runner: JsonataRunner
    validator: ResultValidator
    generator: RuleGenerator


@dataclass(slots=True)
class AsyncDeps:
    llm: AsyncLLMClient
    store: AsyncRuleStore
    config: PipelineConfig
    runner: JsonataRunner
    validator: ResultValidator
    generator: AsyncRuleGenerator


def make_sync_deps(
    *,
    llm: LLMClient,
    store: RuleStore,
    config: PipelineConfig,
    prompt_builder: PromptBuilder | None = None,
) -> SyncDeps:
    return SyncDeps(
        llm=llm,
        store=store,
        config=config,
        runner=JsonataRunner(),
        validator=ResultValidator(),
        generator=RuleGenerator(llm, prompt_builder),
    )


def make_async_deps(
    *,
    llm: AsyncLLMClient,
    store: AsyncRuleStore,
    config: PipelineConfig,
    prompt_builder: PromptBuilder | None = None,
) -> AsyncDeps:
    return AsyncDeps(
        llm=llm,
        store=store,
        config=config,
        runner=JsonataRunner(),
        validator=ResultValidator(),
        generator=AsyncRuleGenerator(llm, prompt_builder),
    )


_SYNC_LOCKS_LOCK = threading.Lock()
_SYNC_LOCKS: dict[str, threading.Lock] = {}
_ASYNC_LOCKS_LOCK = threading.Lock()
_ASYNC_LOCKS: dict[str, asyncio.Lock] = {}


def _sync_lock_for(key: str) -> threading.Lock:
    with _SYNC_LOCKS_LOCK:
        lock = _SYNC_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SYNC_LOCKS[key] = lock
        return lock


def _async_lock_for(key: str) -> asyncio.Lock:
    with _ASYNC_LOCKS_LOCK:
        lock = _ASYNC_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _ASYNC_LOCKS[key] = lock
        return lock


def convert_sync(
    deps: SyncDeps,
    source: Any,
    *,
    target_schema: Any = None,
    target_sample: Any = None,
    description: str | None = None,
    name: str | None = None,
) -> Any:
    target_kind, target_spec = _resolve_target(target_schema, target_sample, description)
    key = build_key(name=name, source=source, target_kind=target_kind, target_spec=target_spec)
    cfg = deps.config

    gen_ctx = GenerationContext(
        source=source,
        target_kind=target_kind,
        target_spec=target_spec,
        sample_truncate_bytes=cfg.sample_truncate_bytes,
    )

    with _sync_lock_for(key):
        rule = deps.store.get(key)
        if rule is not None and _is_expired(rule, cfg.ttl_seconds):
            deps.store.delete(key)
            rule = None

        if rule is None:
            rule = _generate_and_store_sync(deps, key, gen_ctx, target_kind, target_spec, source)

        attempts_remaining = cfg.max_retries

        while True:
            try:
                result = deps.runner.apply(rule.jsonata_rule, source)
                if cfg.validate:
                    deps.validator.validate(result, target_kind, target_spec)
                deps.store.touch(key, success=True)
                return result
            except (JsonataError, ValidationError) as exc:
                deps.store.touch(key, success=False)

                if cfg.on_failure == "raise":
                    raise ConversionError(
                        f"Conversion failed for key {key!r}: {exc}",
                        key=key,
                        last_error=exc,
                    ) from exc

                if attempts_remaining <= 0:
                    raise ConversionError(
                        f"Conversion failed for key {key!r} after retries: {exc}",
                        key=key,
                        last_error=exc,
                    ) from exc

                attempts_remaining -= 1
                error_ctx = ErrorContext(
                    previous_rule=rule.jsonata_rule,
                    error_message=str(exc),
                    observed_result_shape=_safe_shape_from_error(exc),
                )
                new_rule_text = deps.generator.regenerate(
                    gen_ctx, error_ctx, temperature=cfg.temperature, max_tokens=cfg.max_tokens
                )
                rule = _replace_rule_sync(deps, rule, new_rule_text)


def _generate_and_store_sync(
    deps: SyncDeps,
    key: str,
    gen_ctx: GenerationContext,
    target_kind: TargetKind,
    target_spec: Any,
    source: Any,
) -> Rule:
    cfg = deps.config
    rule_text = deps.generator.generate(
        gen_ctx, temperature=cfg.temperature, max_tokens=cfg.max_tokens
    )
    rule = Rule(
        key=key,
        jsonata_rule=rule_text,
        source_shape=shape(source) if isinstance(shape(source), dict) else {"_root": shape(source)},
        target_kind=target_kind,
        target_spec=target_spec if isinstance(target_spec, (dict, list)) else str(target_spec),
        provider=getattr(deps.llm, "provider", "unknown"),
        model=getattr(deps.llm, "model", "unknown"),
    )
    deps.store.put(rule)
    return rule


def _replace_rule_sync(deps: SyncDeps, old: Rule, new_rule_text: str) -> Rule:
    current = deps.store.get(old.key) or old
    new_rule = Rule(
        key=current.key,
        jsonata_rule=new_rule_text,
        source_shape=current.source_shape,
        target_kind=current.target_kind,
        target_spec=current.target_spec,
        provider=current.provider,
        model=current.model,
        version=current.version + 1,
        use_count=current.use_count,
        success_count=current.success_count,
        failure_count=current.failure_count,
        created_at=current.created_at,
    )
    deps.store.put(new_rule)
    return new_rule


async def convert_async(
    deps: AsyncDeps,
    source: Any,
    *,
    target_schema: Any = None,
    target_sample: Any = None,
    description: str | None = None,
    name: str | None = None,
) -> Any:
    target_kind, target_spec = _resolve_target(target_schema, target_sample, description)
    key = build_key(name=name, source=source, target_kind=target_kind, target_spec=target_spec)
    cfg = deps.config

    gen_ctx = GenerationContext(
        source=source,
        target_kind=target_kind,
        target_spec=target_spec,
        sample_truncate_bytes=cfg.sample_truncate_bytes,
    )

    async with _async_lock_for(key):
        rule = await deps.store.aget(key)
        if rule is not None and _is_expired(rule, cfg.ttl_seconds):
            await deps.store.adelete(key)
            rule = None

        if rule is None:
            rule = await _generate_and_store_async(deps, key, gen_ctx, target_kind, target_spec, source)

        attempts_remaining = cfg.max_retries

        while True:
            try:
                result = deps.runner.apply(rule.jsonata_rule, source)
                if cfg.validate:
                    deps.validator.validate(result, target_kind, target_spec)
                await deps.store.atouch(key, success=True)
                return result
            except (JsonataError, ValidationError) as exc:
                await deps.store.atouch(key, success=False)

                if cfg.on_failure == "raise":
                    raise ConversionError(
                        f"Conversion failed for key {key!r}: {exc}",
                        key=key,
                        last_error=exc,
                    ) from exc

                if attempts_remaining <= 0:
                    raise ConversionError(
                        f"Conversion failed for key {key!r} after retries: {exc}",
                        key=key,
                        last_error=exc,
                    ) from exc

                attempts_remaining -= 1
                error_ctx = ErrorContext(
                    previous_rule=rule.jsonata_rule,
                    error_message=str(exc),
                    observed_result_shape=_safe_shape_from_error(exc),
                )
                new_rule_text = await deps.generator.aregenerate(
                    gen_ctx, error_ctx, temperature=cfg.temperature, max_tokens=cfg.max_tokens
                )
                rule = await _replace_rule_async(deps, rule, new_rule_text)


async def _generate_and_store_async(
    deps: AsyncDeps,
    key: str,
    gen_ctx: GenerationContext,
    target_kind: TargetKind,
    target_spec: Any,
    source: Any,
) -> Rule:
    cfg = deps.config
    rule_text = await deps.generator.agenerate(
        gen_ctx, temperature=cfg.temperature, max_tokens=cfg.max_tokens
    )
    src_shape = shape(source)
    rule = Rule(
        key=key,
        jsonata_rule=rule_text,
        source_shape=src_shape if isinstance(src_shape, dict) else {"_root": src_shape},
        target_kind=target_kind,
        target_spec=target_spec if isinstance(target_spec, (dict, list)) else str(target_spec),
        provider=getattr(deps.llm, "provider", "unknown"),
        model=getattr(deps.llm, "model", "unknown"),
    )
    await deps.store.aput(rule)
    return rule


async def _replace_rule_async(deps: AsyncDeps, old: Rule, new_rule_text: str) -> Rule:
    current = await deps.store.aget(old.key) or old
    new_rule = Rule(
        key=current.key,
        jsonata_rule=new_rule_text,
        source_shape=current.source_shape,
        target_kind=current.target_kind,
        target_spec=current.target_spec,
        provider=current.provider,
        model=current.model,
        version=current.version + 1,
        use_count=current.use_count,
        success_count=current.success_count,
        failure_count=current.failure_count,
        created_at=current.created_at,
    )
    await deps.store.aput(new_rule)
    return new_rule


def _safe_shape_from_error(exc: Exception) -> Any | None:
    if isinstance(exc, ValidationError):
        return getattr(exc, "actual", None)
    return None
