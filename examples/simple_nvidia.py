"""Простой sync-пример с NVIDIA NIM в качестве LLM-провайдера.

Запуск:

    python examples/simple_nvidia.py

Что демонстрирует:
  1. Первый вызов convert() — кэш пуст, LLM генерирует JSONata-правило,
     правило сохраняется в sqlite через dbset.
  2. Второй вызов с другим payload (но той же структурой) — попадает в кэш,
     LLM не дёргается.
"""

from __future__ import annotations

import json
from pathlib import Path

from dbset import connect

from translet import Translet, TransletConfig
from translet.exceptions import ConversionError
from translet.llm import Message, nvidia
from translet.store import DbSetStore

# === Конфигурация LLM (NVIDIA NIM) — заполни вручную ===
NVIDIA_API_KEY = "..."
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"

DB_PATH = Path(__file__).parent / "translet_example.db"


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
    if NVIDIA_API_KEY.endswith("REPLACE_ME"):
        raise SystemExit(
            "Заполни NVIDIA_API_KEY в начале файла перед запуском примера."
        )

    if DB_PATH.exists():
        DB_PATH.unlink()

    llm = \
        (nvidia(NVIDIA_MODEL, api_key=NVIDIA_API_KEY))
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
