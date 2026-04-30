"""Простой sync-пример с NVIDIA NIM в качестве LLM-провайдера (без диагностики).

Запуск:

    python examples/simple_nvidia_clean.py

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
from translet.llm import nvidia
from translet.store import DbSetStore

# === Конфигурация LLM (NVIDIA NIM) — заполни вручную ===
NVIDIA_API_KEY = "..."
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"

DB_PATH = Path(__file__).parent / "translet_example.db"


def main() -> None:
    DB_PATH.unlink() if DB_PATH.exists() else None

    llm = nvidia(NVIDIA_MODEL, api_key=NVIDIA_API_KEY)
    db = connect(f"sqlite:///{DB_PATH}")
    store = DbSetStore(db, table="example_rules")
    t = Translet(llm=llm, store=store, config=TransletConfig(max_retries=2))

    source_a = {"first_name": "Alice", "last_name": "Smith", "age": 30}
    source_b = {"first_name": "Bob", "last_name": "Jones", "age": 42}
    target_sample = {"full_name": "Alice Smith", "age": 30}

    print("=== Call 1 (cache miss) ===")
    print("source:", json.dumps(source_a))
    result_a = t.transjson.convert(source_a, target_sample=target_sample, name="full_name_v1")
    print("result:", json.dumps(result_a))

    print("\n=== Call 2 (cache hit) ===")
    print("source:", json.dumps(source_b))
    result_b = t.transjson.convert(source_b, target_sample=target_sample, name="full_name_v1")
    print("result:", json.dumps(result_b))

    db.close()


if __name__ == "__main__":
    main()
