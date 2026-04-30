"""Универсальный sync-пример: вся конфигурация через переменные окружения / .env.

Поддерживаемые переменные:

    TRANSLET_LLM_PROVIDER   openai | azure | groq | nvidia
    TRANSLET_LLM_MODEL      имя модели (обязательно)
    TRANSLET_LLM_BASE_URL   опциональный override base URL

    OPENAI_API_KEY / AZURE_OPENAI_API_KEY / GROQ_API_KEY / NVIDIA_API_KEY   API-ключ
    TRANSLET_API_KEY                                                       универсальный fallback
    AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_VERSION                       только для Azure

    TRANSLET_DB_PATH        connection string для dbset (default: sqlite:///translet.db)
    TRANSLET_DB_TABLE       имя таблицы (default: translet_rules)
    TRANSLET_TTL_SECONDS    TTL правил (default: без TTL)
    TRANSLET_MAX_RETRIES    кол-во попыток regenerate (default: 2)

Запуск:

    cp examples/.env.generic.example examples/.env
    # отредактируй examples/.env под свой провайдер
    python examples/simple_from_env.py
"""

from __future__ import annotations

import json
from pathlib import Path

from translet import Translet

ENV_PATH = Path(__file__).parent.parent / "nvidia.env"
DB_PATH = Path(__file__).parent / "translet_example.db"


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    t = Translet.from_env(env_file=ENV_PATH, db_path=f"sqlite:///{DB_PATH}")
    print(f"provider={t.llm.provider}  model={t.llm.model}")

    source_a = {"first_name": "Alice", "last_name": "Smith", "age": 30}
    source_b = {"first_name": "Bob", "last_name": "Jones", "age": 42}
    target_sample = {"full_name": "Alice Smith", "age": 30}

    print("\n=== Call 1 (cache miss) ===")
    print("source:", json.dumps(source_a))
    result_a = t.transjson.convert(source_a, target_sample=target_sample, name="full_name_v1")
    print("result:", json.dumps(result_a))

    print("\n=== Call 2 (cache hit) ===")
    print("source:", json.dumps(source_b))
    result_b = t.transjson.convert(source_b, target_sample=target_sample, name="full_name_v1")
    print("result:", json.dumps(result_b))


if __name__ == "__main__":
    main()
