# translet

JSON-конверсии через **JSONata**-правила, которые генерируются **LLM** и кэшируются в БД (через [`dbset`](https://pypi.org/project/dbset/)).

При первом вызове `convert` пакет:

1. строит ключ кэша (по явному имени или по структурной форме входа + цели);
2. если правила нет — просит LLM сгенерировать JSONata-выражение и сохраняет его;
3. применяет правило через [`jsonata-python`](https://pypi.org/project/jsonata-python/);
4. валидирует результат против целевой спецификации (JSON Schema или образца);
5. при ошибке — регенерирует правило с контекстом ошибки и повторяет (по умолчанию до 2 раз).

Следующие вызовы с той же структурой попадают в кэш — без обращения к LLM.

## Содержание

- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Три способа задать цель](#три-способа-задать-цель)
- [Конфигурация через `.env`](#конфигурация-через-env)
- [Async](#async)
- [Ручная сборка (без `from_env`)](#ручная-сборка-без-from_env)
- [Управление кэшем](#управление-кэшем)
- [Статистика](#статистика)
- [Обработка ошибок](#обработка-ошибок)
- [Расширение](#расширение)
- [Разработка](#разработка)

## Установка

```bash
pip install translet[all-llm]
```

`all-llm` ставит `openai` SDK, через который пакет работает с OpenAI, Azure OpenAI, Groq и NVIDIA NIM. Можно поставить точечно: `translet[openai]`, `translet[azure]`, `translet[groq]`, `translet[nvidia]`.

## Быстрый старт

```python
from translet import Translet

t = Translet.from_env()  # читает TRANSLET_LLM_*, TRANSLET_DB_* и т.д.

result = t.transjson.convert(
    {"user": {"name": "Alice", "age": 30}},
    target_sample={"name": "x", "age": 0},
)
# {"name": "Alice", "age": 30}
```

## Три способа задать цель

`convert(source, *, target_schema=None, target_sample=None, description=None, name=None)` принимает **одну** из трёх целевых спецификаций. Они влияют и на промпт LLM, и на пост-валидацию.

### 1. JSON Schema — строгая валидация

```python
schema = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["full_name", "age"],
}

result = t.transjson.convert(
    {"first_name": "Alice", "last_name": "Smith", "age": 30},
    target_schema=schema,
)
# {"full_name": "Alice Smith", "age": 30}
```

После генерации правила результат прогоняется через `jsonschema`. Несоответствие → `ValidationError` → регенерация (до `max_retries`).

### 2. Образец (target_sample) — структурное соответствие

LLM получает пример итоговой формы. Валидация — по совпадению типов/ключей образца.

```python
result = t.transjson.convert(
    {"first_name": "Alice", "last_name": "Smith"},
    target_sample={"full_name": "Alice Smith"},
)
```

### 3. Описание (description) + явное имя

Когда форма цели тривиальна или результат скалярный — задайте задачу текстом. Обязательно укажите `name=` для явного ключа кэша.

```python
result = t.transjson.convert(
    {"items": [{"v": 1}, {"v": 2}, {"v": 3}]},
    description="sum of all v values",
    name="sum_v_rule",
)
# 6
```

### Ключи кэша

- `name="foo"` → ключ `name:foo` (стабильный, переживает изменения структуры входа).
- Без `name` → ключ `hash:<sha>` от формы входа + цели. Любое изменение схемы — новый ключ.

## Конфигурация через `.env`

`Translet.from_env(env_file=...)` грузит `.env`-файл и читает переменные окружения. Поддерживаются стандартные `KEY=VALUE`, комментарии `#`, опциональные кавычки.

```python
from translet import Translet

t = Translet.from_env(env_file=".env")
```

### Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `TRANSLET_LLM_PROVIDER` | `openai` / `azure` / `groq` / `nvidia` |
| `TRANSLET_LLM_MODEL` | Имя модели (обязательно) |
| `TRANSLET_LLM_BASE_URL` | Override базового URL |
| `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY` / `GROQ_API_KEY` / `NVIDIA_API_KEY` | API-ключ, специфичный для провайдера (рекомендуется — совпадает с конвенцией SDK) |
| `TRANSLET_API_KEY` | Универсальный fallback, если provider-specific не задан |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_VERSION` | Только для Azure |
| `TRANSLET_DB_PATH` | Connection string для `dbset` (default: `sqlite:///translet.db`) |
| `TRANSLET_DB_TABLE` | Имя таблицы (default: `translet_rules`) |
| `TRANSLET_TTL_SECONDS` | TTL правил (default: без TTL) |
| `TRANSLET_MAX_RETRIES` | Количество попыток regenerate (default: 2) |

Provider-specific ключ имеет приоритет над `TRANSLET_API_KEY`.

### Override параметров из кода

`Translet.from_env(...)` принимает kwargs, которые перетирают значения из `.env`/`os.environ`:

```python
from pathlib import Path
from translet import Translet

DB_PATH = Path("./cache/rules.db")

t = Translet.from_env(
    env_file=".env",
    db_path=f"sqlite:///{DB_PATH}",   # перетирает TRANSLET_DB_PATH
    max_retries=5,                    # перетирает TRANSLET_MAX_RETRIES
    api_key="sk-...",                 # уходит в provider-specific переменную
)
```

Доступны: `provider`, `model`, `base_url`, `api_key`, `db_path`, `db_table`, `ttl_seconds`, `max_retries`. Любой `None` — оставить значение из `.env`/окружения. Флаг `override=True` для `load_dotenv` принудительно перетирает `os.environ` значениями из файла.

### Загрузка `.env` отдельно от Translet

```python
from translet import load_dotenv

load_dotenv(".env")               # setdefault-семантика
load_dotenv(".env", override=True)  # перетереть существующие
```

## Async

```python
import asyncio
from translet import AsyncTranslet

async def main():
    t = await AsyncTranslet.from_env(env_file=".env")
    result = await t.transjson.aconvert(
        {"user": {"name": "Alice"}},
        target_sample={"name": "x"},
    )
    print(result)

asyncio.run(main())
```

`AsyncTranslet.from_env` принимает те же overrides, что и sync-версия.

## Ручная сборка (без `from_env`)

```python
from dbset import connect
from translet import Translet, TransletConfig
from translet.llm import openai
from translet.store import DbSetStore

db = connect("sqlite:///translet.db")
t = Translet(
    llm=openai("gpt-4o", api_key="..."),
    store=DbSetStore(db, table="my_rules"),
    config=TransletConfig(max_retries=2, ttl_seconds=None),
)
```

Доступные фабрики LLM: `openai`, `azure`, `groq`, `nvidia` (sync) и `aopenai`, `aazure`, `agroq`, `anvidia` (async).

`DbSetStore` не владеет соединением — закрывать `db` нужно явно (`db.close()`). Это позволяет переиспользовать одно подключение для нескольких таблиц/хранилищ.

## Управление кэшем

```python
# Явная инвалидация по имени или ключу
t.transjson.invalidate("sum_v_rule")
t.transjson.invalidate("name:full_name_v1")
t.transjson.invalidate("hash:abc123...")

# Ручная чистка устаревших по TTL (возвращает количество удалённых)
removed = t.transjson.evict_expired(ttl_seconds=86400)
```

Если в `TransletConfig` задан `ttl_seconds`, то `evict_expired()` без аргумента возьмёт его как дефолт.

## Статистика

`compute_stats(rules)` агрегирует кэш правил, `format_stats(stats)` рендерит в текст.

```python
from translet import Translet, compute_stats, format_stats

t = Translet.from_env()
rules = t.store.list(limit=10000)
print(format_stats(compute_stats(rules, top=10)))
```

Поля `RuleStats`: `total_rules`, `total_uses`, `total_successes`, `total_failures`, `success_rate`, `by_provider`, `by_model`, `top_by_usage`, `oldest_created`, `newest_created`, `last_used`.

CLI-утилита для быстрой проверки:

```bash
python examples/show_stats.py --env-file .env
python examples/show_stats.py --db-path "sqlite:///./cache/rules.db" --top 10
```

## Обработка ошибок

Все исключения наследуются от `TransletError`:

```python
from translet import (
    ConversionError,      # все retry исчерпаны
    RuleGenerationError,  # LLM не смог выдать валидное JSONata
    JsonataError,         # ошибка компиляции/выполнения JSONata
    ValidationError,      # результат не прошёл схему/образец
    StoreError,           # сбой хранилища
)

try:
    result = t.transjson.convert(source, target_sample=sample)
except ConversionError as exc:
    print(f"failed for key={exc.key}, last error: {exc.last_error!r}")
```

`on_failure` в `TransletConfig` управляет поведением: `"regenerate"` (по умолчанию — пытаться заново) или `"raise"` (сразу падать).

## Расширение

### Свой LLM-провайдер

```python
from translet.llm import LLMClient, Message

class MyLLM:
    provider = "my-provider"
    model = "my-model"

    def complete(self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int = 2048) -> str:
        ...  # вернуть текст ответа

t = Translet(llm=MyLLM(), store=store)
```

`LLMClient` — это `Protocol` (`runtime_checkable`), наследовать необязательно — достаточно структурного соответствия. Async-вариант: `AsyncLLMClient` с методом `acomplete`.

### Своё хранилище

Реализуйте `translet.store.RuleStore` (или `AsyncRuleStore`) — методы `get`, `put`, `touch`, `delete`, `evict_expired`, `list`. См. `DbSetStore` как образец.

### Свой системный промпт

```python
from translet import TransletConfig

config = TransletConfig(system_prompt="You are a JSONata generator. Output only the expression.")
```

Для полного контроля над промптом передайте свой `prompt_builder=YourPromptBuilder()` (см. `translet.transjson.PromptBuilder`).

## Разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all-llm]"
pytest -q
```

Структура проекта:

```
src/translet/
  core.py              # Translet / AsyncTranslet, from_env, load_dotenv
  llm/                 # LLMClient Protocol + OpenAI-compatible клиенты
  store/               # RuleStore Protocol + DbSetStore
  transjson/           # пайплайн convert (генерация → JSONata → валидация → retry)
  stats.py             # агрегация статистики по кэшу
  exceptions.py
examples/
  simple_nvidia.py        # минимальный пример с NVIDIA NIM
  simple_from_env.py      # универсальный пример через .env
  show_stats.py           # CLI: статистика по кэшу
```

## Сборка и публикация

```bash
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

## Лицензия

MIT
