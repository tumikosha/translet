from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ..exceptions import RuleGenerationError
from ..llm import AsyncLLMClient, LLMClient, Message
from ..store import TargetKind
from .key_builder import shape

DEFAULT_SYSTEM_PROMPT = (
    "You are a JSONata rule generator. Given a source JSON value and a target "
    "specification, output a single valid JSONata expression that converts the "
    "source into the target.\n"
    "\n"
    "JSONata syntax notes (follow strictly):\n"
    "- Reference input fields by name WITHOUT the `$` prefix. "
    "Use `first_name`, NOT `$first_name`. The `$` prefix is reserved for "
    "user-defined variables (e.g. `$myVar := ...`) and built-in functions "
    "(e.g. `$sum`, `$map`, `$length`).\n"
    "- Access nested fields with dot notation: `user.name`, `items[0].id`.\n"
    "- Construct objects with `{\"key\": expression, ...}`. The whole "
    "expression yields the resulting value.\n"
    "- String concatenation uses `&`, not `+`.\n"
    "- Conditionals use `condition ? then_expr : else_expr`.\n"
    "- Map over arrays with `array.{...}` or `array.($expr)`.\n"
    "\n"
    "Examples:\n"
    "  Source: {\"first_name\": \"A\", \"last_name\": \"B\", \"age\": 30}\n"
    "  Target sample: {\"full_name\": \"A B\", \"age\": 30}\n"
    "  Rule: {\"full_name\": first_name & \" \" & last_name, \"age\": age}\n"
    "\n"
    "  Source: {\"items\": [{\"v\": 1}, {\"v\": 2}, {\"v\": 3}]}\n"
    "  Target description: sum of all v\n"
    "  Rule: $sum(items.v)\n"
    "\n"
    "Output ONLY the JSONata expression — no prose, no markdown fences, "
    "no explanations, no leading/trailing comments."
)

_FENCE_RE = re.compile(r"^\s*```(?:jsonata|json)?\s*\n(.*?)\n\s*```\s*$", re.DOTALL)


@dataclass(slots=True)
class GenerationContext:
    source: Any
    target_kind: TargetKind
    target_spec: Any
    sample_truncate_bytes: int = 2048


@dataclass(slots=True)
class ErrorContext:
    previous_rule: str
    error_message: str
    observed_result_shape: Any | None = None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, total {len(text)} bytes]"


class PromptBuilder:
    def __init__(self, system_prompt: str | None = None):
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

    def build(self, ctx: GenerationContext, error: ErrorContext | None = None) -> list[Message]:
        source_shape = shape(ctx.source)
        source_sample = _truncate(json.dumps(ctx.source, indent=2, default=str), ctx.sample_truncate_bytes)

        parts: list[str] = [
            "Convert the SOURCE into the form described by TARGET.",
            "",
            "SOURCE_SHAPE:",
            json.dumps(source_shape, indent=2),
            "",
            "SOURCE_SAMPLE:",
            source_sample,
            "",
            f"TARGET_KIND: {ctx.target_kind}",
        ]

        if ctx.target_kind == "schema":
            parts += ["TARGET_SCHEMA:", json.dumps(ctx.target_spec, indent=2)]
        elif ctx.target_kind == "sample":
            parts += [
                "TARGET_SAMPLE:",
                json.dumps(ctx.target_spec, indent=2, default=str),
                "",
                "TARGET_SHAPE:",
                json.dumps(shape(ctx.target_spec), indent=2),
            ]
        else:  # description
            parts += ["TARGET_DESCRIPTION:", str(ctx.target_spec)]

        if error is not None:
            parts += [
                "",
                "PREVIOUS_ATTEMPT_FAILED:",
                "Previous JSONata expression:",
                error.previous_rule,
                "",
                f"Error: {error.error_message}",
            ]
            if error.observed_result_shape is not None:
                parts += ["Observed result shape:", json.dumps(error.observed_result_shape, indent=2)]
            parts += ["", "Produce a corrected JSONata expression."]

        user_content = "\n".join(parts)
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]


def _post_process(raw: str) -> str:
    text = raw.strip()
    match = _FENCE_RE.match(text)
    if match:
        text = match.group(1).strip()
    if not text:
        raise RuleGenerationError("LLM returned an empty response.")
    return text


class RuleGenerator:
    def __init__(self, llm: LLMClient, prompt_builder: PromptBuilder | None = None):
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()

    def generate(self, ctx: GenerationContext, *, temperature: float = 0.0, max_tokens: int = 2048) -> str:
        messages = self.prompt_builder.build(ctx)
        return self._call(messages, temperature, max_tokens)

    def regenerate(
        self,
        ctx: GenerationContext,
        error: ErrorContext,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        messages = self.prompt_builder.build(ctx, error=error)
        return self._call(messages, temperature, max_tokens)

    def _call(self, messages: list[Message], temperature: float, max_tokens: int) -> str:
        try:
            raw = self.llm.complete(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            raise RuleGenerationError(f"LLM call failed: {exc}") from exc
        return _post_process(raw)


class AsyncRuleGenerator:
    def __init__(self, llm: AsyncLLMClient, prompt_builder: PromptBuilder | None = None):
        self.llm = llm
        self.prompt_builder = prompt_builder or PromptBuilder()

    async def agenerate(
        self, ctx: GenerationContext, *, temperature: float = 0.0, max_tokens: int = 2048
    ) -> str:
        messages = self.prompt_builder.build(ctx)
        return await self._call(messages, temperature, max_tokens)

    async def aregenerate(
        self,
        ctx: GenerationContext,
        error: ErrorContext,
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> str:
        messages = self.prompt_builder.build(ctx, error=error)
        return await self._call(messages, temperature, max_tokens)

    async def _call(self, messages: list[Message], temperature: float, max_tokens: int) -> str:
        try:
            raw = await self.llm.acomplete(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception as exc:
            raise RuleGenerationError(f"LLM call failed: {exc}") from exc
        return _post_process(raw)
