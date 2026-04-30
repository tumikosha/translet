import pytest

from translet.exceptions import RuleGenerationError
from translet.transjson import (
    AsyncRuleGenerator,
    ErrorContext,
    GenerationContext,
    PromptBuilder,
    RuleGenerator,
)


def _ctx(target_kind="sample", target_spec=None):
    return GenerationContext(
        source={"a": 1},
        target_kind=target_kind,
        target_spec=target_spec if target_spec is not None else {"value": 1},
    )


def test_prompt_includes_source_shape_and_sample():
    builder = PromptBuilder()
    messages = builder.build(_ctx())
    user = messages[1]["content"]
    assert "SOURCE_SHAPE" in user
    assert "SOURCE_SAMPLE" in user
    assert "TARGET_SAMPLE" in user


def test_prompt_for_schema_kind():
    builder = PromptBuilder()
    messages = builder.build(_ctx(target_kind="schema", target_spec={"type": "object"}))
    assert "TARGET_SCHEMA" in messages[1]["content"]


def test_prompt_for_description_kind():
    builder = PromptBuilder()
    messages = builder.build(_ctx(target_kind="description", target_spec="flatten the list"))
    assert "TARGET_DESCRIPTION" in messages[1]["content"]
    assert "flatten the list" in messages[1]["content"]


def test_prompt_includes_error_context_on_regenerate():
    builder = PromptBuilder()
    err = ErrorContext(previous_rule="$.foo", error_message="boom", observed_result_shape={"a": "<int>"})
    messages = builder.build(_ctx(), error=err)
    user = messages[1]["content"]
    assert "PREVIOUS_ATTEMPT_FAILED" in user
    assert "$.foo" in user
    assert "boom" in user


def test_post_processing_strips_markdown_fences(fake_llm):
    fake_llm.queue("```jsonata\n$sum(items.x)\n```")
    rule = RuleGenerator(fake_llm).generate(_ctx())
    assert rule == "$sum(items.x)"


def test_post_processing_strips_plain_fences(fake_llm):
    fake_llm.queue("```\n$.user.name\n```")
    rule = RuleGenerator(fake_llm).generate(_ctx())
    assert rule == "$.user.name"


def test_empty_response_raises(fake_llm):
    fake_llm.queue("   ")
    with pytest.raises(RuleGenerationError):
        RuleGenerator(fake_llm).generate(_ctx())


def test_llm_failure_raises_rule_generation_error():
    class BoomLLM:
        provider = "fake"
        model = "boom"

        def complete(self, *args, **kwargs):
            raise RuntimeError("network down")

    with pytest.raises(RuleGenerationError):
        RuleGenerator(BoomLLM()).generate(_ctx())


async def test_async_generator_returns_clean_rule(fake_async_llm):
    fake_async_llm.queue("$sum(x)")
    rule = await AsyncRuleGenerator(fake_async_llm).agenerate(_ctx())
    assert rule == "$sum(x)"
