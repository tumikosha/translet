"""CLI-утилита: статистика по кэшу translet-правил.

Запуск:

    python examples/show_stats.py
    python examples/show_stats.py --env-file nvidia.env
    python examples/show_stats.py --db-path "sqlite:///examples/translet_example.db"
    python examples/show_stats.py --top 10

Подключение к хранилищу берётся из (по приоритету):
  1) флагов CLI
  2) переменных окружения (TRANSLET_DB_PATH / TRANSLET_DB_TABLE)
  3) дефолтов (sqlite:///translet.db / translet_rules)
"""

from __future__ import annotations

import argparse
import os

from dbset import connect

from translet import compute_stats, format_stats, load_dotenv
from translet.store import DEFAULT_TABLE, DbSetStore

DEFAULT_DB_URL = "sqlite:///translet.db"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Показать статистику по translet-кэшу.")
    p.add_argument("--env-file", help="путь к .env (опционально)")
    p.add_argument("--db-path", help="dbset connection string (override TRANSLET_DB_PATH)")
    p.add_argument("--db-table", help="имя таблицы (override TRANSLET_DB_TABLE)")
    p.add_argument("--top", type=int, default=5, help="сколько правил показать в топе по usage (default: 5)")
    p.add_argument("--limit", type=int, default=10000, help="макс. число правил для выгрузки (default: 10000)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.env_file:
        load_dotenv(args.env_file)

    db_url = args.db_path or os.environ.get("TRANSLET_DB_PATH") or DEFAULT_DB_URL
    table = args.db_table or os.environ.get("TRANSLET_DB_TABLE") or DEFAULT_TABLE

    print(f"db:    {db_url}")
    print(f"table: {table}")
    print()

    db = connect(db_url)
    try:
        store = DbSetStore(db, table=table)
        rules = store.list(limit=args.limit)
        stats = compute_stats(rules, top=args.top)
        print(format_stats(stats))
    finally:
        db.close()


if __name__ == "__main__":
    main()
