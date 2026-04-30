from datetime import UTC

import pytest

from translet.exceptions import ConversionError
from translet.transjson import (
    PipelineConfig,
    convert_async,
    convert_sync,
    make_async_deps,
    make_sync_deps,
)


def _deps(fake_llm, memory_store, **cfg_overrides):
    cfg = PipelineConfig(**cfg_overrides)
    return make_sync_deps(llm=fake_llm, store=memory_store, config=cfg)


def _adeps(fake_async_llm, memory_async_store, **cfg_overrides):
    cfg = PipelineConfig(**cfg_overrides)
    return make_async_deps(llm=fake_async_llm, store=memory_async_store, config=cfg)


def test_cache_miss_then_hit_avoids_second_llm_call(fake_llm, memory_store):
    fake_llm.queue("{'name': user.name}")
    deps = _deps(fake_llm, memory_store)

    r1 = convert_sync(deps, {"user": {"name": "Alice"}}, target_sample={"name": "x"})
    assert r1 == {"name": "Alice"}

    r2 = convert_sync(deps, {"user": {"name": "Bob"}}, target_sample={"name": "x"})
    assert r2 == {"name": "Bob"}
    assert len(fake_llm.calls) == 1


def test_named_rule_uses_same_key_for_different_payloads(fake_llm, memory_store):
    fake_llm.queue("{'name': user.name}")
    deps = _deps(fake_llm, memory_store)

    convert_sync(deps, {"user": {"name": "A"}, "extra": 1}, target_sample={"name": "x"}, name="my_rule")
    convert_sync(
        deps,
        {"user": {"name": "B"}, "totally": "different"},
        target_sample={"name": "x"},
        name="my_rule",
    )
    assert len(fake_llm.calls) == 1


def test_different_target_specs_have_different_keys(fake_llm, memory_store):
    fake_llm.queue("{'name': user.name}", "{'age': user.age}")
    deps = _deps(fake_llm, memory_store)

    convert_sync(deps, {"user": {"name": "A", "age": 30}}, target_sample={"name": "x"})
    convert_sync(deps, {"user": {"name": "A", "age": 30}}, target_sample={"age": 1})
    assert len(fake_llm.calls) == 2


def test_regenerate_on_jsonata_compile_error(fake_llm, memory_store):
    fake_llm.queue("(((", "{'name': user.name}")
    deps = _deps(fake_llm, memory_store)

    result = convert_sync(deps, {"user": {"name": "Z"}}, target_sample={"name": "x"})
    assert result == {"name": "Z"}
    assert len(fake_llm.calls) == 2


def test_regenerate_on_validation_failure(fake_llm, memory_store):
    fake_llm.queue("user.name", "{'age': user.age}")
    deps = _deps(fake_llm, memory_store)

    result = convert_sync(deps, {"user": {"name": "Z", "age": 42}}, target_sample={"age": 1})
    assert result == {"age": 42}
    assert len(fake_llm.calls) == 2


def test_max_retries_exhausted_raises_conversion_error(fake_llm, memory_store):
    fake_llm.queue("(((", "(((", "(((")
    deps = _deps(fake_llm, memory_store, max_retries=2)

    with pytest.raises(ConversionError):
        convert_sync(deps, {"user": {"name": "X"}}, target_sample={"name": "x"})


def test_on_failure_raise_propagates_first_error(fake_llm, memory_store):
    fake_llm.queue("(((")
    deps = _deps(fake_llm, memory_store, on_failure="raise")

    with pytest.raises(ConversionError):
        convert_sync(deps, {"user": {"name": "X"}}, target_sample={"name": "x"})
    assert len(fake_llm.calls) == 1


def test_validate_false_accepts_shape_mismatch(fake_llm, memory_store):
    fake_llm.queue("user.name")
    deps = _deps(fake_llm, memory_store, validate=False)

    result = convert_sync(deps, {"user": {"name": "Alice"}}, target_sample={"full_name": "x"})
    assert result == "Alice"
    assert len(fake_llm.calls) == 1


def test_validate_false_still_regenerates_on_jsonata_error(fake_llm, memory_store):
    fake_llm.queue("(((", "user.name")
    deps = _deps(fake_llm, memory_store, validate=False)

    result = convert_sync(deps, {"user": {"name": "Alice"}}, target_sample={"full_name": "x"})
    assert result == "Alice"
    assert len(fake_llm.calls) == 2


def test_validate_false_with_raise_on_jsonata_error(fake_llm, memory_store):
    fake_llm.queue("(((")
    deps = _deps(fake_llm, memory_store, validate=False, on_failure="raise")

    with pytest.raises(ConversionError):
        convert_sync(deps, {"user": {"name": "X"}}, target_sample={"full_name": "x"})
    assert len(fake_llm.calls) == 1


def test_ttl_expiry_triggers_regeneration(fake_llm, memory_store):
    from datetime import datetime, timedelta

    fake_llm.queue("{'name': user.name}", "{'name': user.name}")
    deps = _deps(fake_llm, memory_store, ttl_seconds=1)

    convert_sync(deps, {"user": {"name": "A"}}, target_sample={"name": "x"})
    assert len(fake_llm.calls) == 1

    cached = list(memory_store.list())[0]
    cached.last_used_at = datetime.now(UTC) - timedelta(seconds=10)
    memory_store.put(cached)

    convert_sync(deps, {"user": {"name": "B"}}, target_sample={"name": "x"})
    assert len(fake_llm.calls) == 2


def test_touch_increments_success_and_failure_counts(fake_llm, memory_store):
    fake_llm.queue("(((", "{'name': user.name}")
    deps = _deps(fake_llm, memory_store)

    convert_sync(deps, {"user": {"name": "A"}}, target_sample={"name": "x"})
    rule = list(memory_store.list())[0]
    assert rule.success_count == 1
    assert rule.failure_count == 1
    assert rule.use_count == 2
    assert rule.version == 2


async def test_async_cache_miss_then_hit(fake_async_llm, memory_async_store):
    fake_async_llm.queue("{'name': user.name}")
    deps = _adeps(fake_async_llm, memory_async_store)

    r1 = await convert_async(deps, {"user": {"name": "Alice"}}, target_sample={"name": "x"})
    r2 = await convert_async(deps, {"user": {"name": "Bob"}}, target_sample={"name": "x"})
    assert r1 == {"name": "Alice"} and r2 == {"name": "Bob"}
    assert len(fake_async_llm.calls) == 1


def test_invalid_target_kwargs(fake_llm, memory_store):
    deps = _deps(fake_llm, memory_store)
    with pytest.raises(ValueError):
        convert_sync(deps, {"a": 1})  # nothing provided
    with pytest.raises(ValueError):
        convert_sync(deps, {"a": 1}, target_schema={}, target_sample={})  # two provided
