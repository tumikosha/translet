"""Простой sync-пример с NVIDIA NIM. Конфиг читается из .env рядом с файлом.

Запуск:

    cp examples/.env.example examples/.env
    # отредактируй examples/.env, подставь NVIDIA_API_KEY
    python examples/simple_nvidia_env.py

Что демонстрирует:
  1. Первый вызов convert() — кэш пуст, LLM генерирует JSONata-правило,
     правило сохраняется в sqlite через dbset.
  2. Второй вызов с другим payload (но той же структурой) — попадает в кэш,
     LLM не дёргается.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dbset import connect

from translet import Translet, TransletConfig
from translet.exceptions import ConversionError
from translet.llm import Message, nvidia
from translet.store import DbSetStore

ENV_PATH = Path(__file__).parent / ".env"
DB_PATH = Path(__file__).parent / "translet_example.db"


def load_env(path: Path) -> None:
    """Минимальный парсер .env: KEY=VALUE, # комментарии, опциональные кавычки."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class LoggingLLM:
    """Печатает каждый запрос/ответ LLM — для диагностики."""

    def __init__(self, inner):
        self._inner = inner
        self.provider = inner.provider
        self.model = inner.model

    def complete(self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int = 2048) -> str:
        print(f"\n  [LLM call → {self.provider}/{self.model}]")
        raw = self._inner.complete(messages, temperature=temperature, max_tokens=max_tokens)
        print(f"  [LLM raw response]:\n    {raw!r}")
        return raw


def dump_store(store: DbSetStore, label: str) -> None:
    print(f"\n=== Stored rules ({label}) ===")
    rules = store.list()
    if not rules:
        print("  (empty)")
        return
    for r in rules:
        print(f"  key={r.key}")
        print(f"    version={r.version}  use={r.use_count}  ok={r.success_count}  fail={r.failure_count}")
        print(f"    jsonata: {r.jsonata_rule!r}")


def main() -> None:
    load_env(ENV_PATH)

    api_key = os.environ.get("NVIDIA_API_KEY")
    model = os.environ.get("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")
    if not api_key:
        raise SystemExit(
            f"NVIDIA_API_KEY не задан. Создай {ENV_PATH} (см. examples/.env.example)."
        )

    if DB_PATH.exists():
        DB_PATH.unlink()

    llm = LoggingLLM(nvidia(model, api_key=api_key))
    db = connect(f"sqlite:///{DB_PATH}")
    store = DbSetStore(db, table="example_rules")
    t = Translet(llm=llm, store=store, config=TransletConfig(max_retries=2))

    source_a = {"first_name": "Alice", "last_name": "Smith", "age": 30}
    source_b = {"first_name": "Bob", "last_name": "Jones", "age": 42}
    target_sample = {"full_name": "Alice Smith", "age": 30}

    print("=== Call 1 (cache miss — expect an LLM round-trip) ===")
    print("source:", json.dumps(source_a))
    print("target_sample:", json.dumps(target_sample))
    try:
        result_a = t.transjson.convert(source_a, target_sample=target_sample, name="full_name_v1")
        print("result:", json.dumps(result_a))
    except ConversionError as exc:
        print(f"\n[ConversionError] {exc}")
        print(f"  last underlying error: {exc.last_error!r}")
        dump_store(store, "after failure")
        db.close()
        raise SystemExit(1) from exc

    print("\n=== Call 2 (cache hit — same rule, no LLM call) ===")
    print("source:", json.dumps(source_b))
    result_b = t.transjson.convert(source_b, target_sample=target_sample, name="full_name_v1")
    print("result:", json.dumps(result_b))

    dump_store(store, "after both calls")
    db.close()


if __name__ == "__main__":
    main()