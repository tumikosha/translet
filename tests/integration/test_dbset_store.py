from datetime import UTC, datetime, timedelta

import pytest

from translet.store import DbSetStore, Rule


@pytest.fixture
def db(tmp_path):
    from dbset import connect

    db_path = tmp_path / "test_translet.db"
    conn = connect(f"sqlite:///{db_path}")
    yield conn
    conn.close()


def _rule(key="hash:abc", suffix="") -> Rule:
    return Rule(
        key=key,
        jsonata_rule=f"$sum(items.value){suffix}",
        source_shape={"items": [{"value": "<int>"}]},
        target_kind="schema",
        target_spec={"type": "integer"},
        provider="openai",
        model="gpt-4o",
    )


def test_put_and_get_round_trip(db):
    store = DbSetStore(db, table="rules_a")
    rule = _rule()
    store.put(rule)
    fetched = store.get(rule.key)
    assert fetched is not None
    assert fetched.key == rule.key
    assert fetched.jsonata_rule == rule.jsonata_rule
    assert fetched.source_shape == rule.source_shape
    assert fetched.target_spec == rule.target_spec
    assert fetched.provider == "openai"
    assert isinstance(fetched.created_at, datetime)


def test_get_missing_returns_none(db):
    store = DbSetStore(db, table="rules_b")
    assert store.get("nope") is None


def test_put_is_upsert(db):
    store = DbSetStore(db, table="rules_c")
    store.put(_rule())
    store.put(_rule(suffix=" * 2"))
    fetched = store.get("hash:abc")
    assert fetched.jsonata_rule.endswith("* 2")
    assert len(store.list()) == 1


def test_touch_updates_counters(db):
    store = DbSetStore(db, table="rules_d")
    store.put(_rule())
    store.touch("hash:abc", success=True)
    store.touch("hash:abc", success=False)
    fetched = store.get("hash:abc")
    assert fetched.use_count == 2
    assert fetched.success_count == 1
    assert fetched.failure_count == 1


def test_delete_removes_rule(db):
    store = DbSetStore(db, table="rules_e")
    store.put(_rule())
    store.delete("hash:abc")
    assert store.get("hash:abc") is None


def test_evict_expired_removes_old_rules(db):
    store = DbSetStore(db, table="rules_f")
    fresh = _rule(key="hash:fresh")
    expired = _rule(key="hash:expired")
    expired.last_used_at = datetime.now(UTC) - timedelta(seconds=600)
    store.put(fresh)
    store.put(expired)
    removed = store.evict_expired(60)
    assert removed == 1
    assert store.get("hash:expired") is None
    assert store.get("hash:fresh") is not None


def test_table_isolation(db):
    store_a = DbSetStore(db, table="orders")
    store_b = DbSetStore(db, table="invoices")
    store_a.put(_rule(key="hash:order"))
    assert store_a.get("hash:order") is not None
    assert store_b.get("hash:order") is None


def test_list_returns_all_rules(db):
    store = DbSetStore(db, table="rules_g")
    store.put(_rule(key="hash:1"))
    store.put(_rule(key="hash:2"))
    rules = store.list()
    keys = {r.key for r in rules}
    assert keys == {"hash:1", "hash:2"}


def test_target_spec_text_round_trip(db):
    store = DbSetStore(db, table="rules_h")
    rule = _rule()
    rule.target_kind = "description"
    rule.target_spec = "make a flat list of names"
    store.put(rule)
    fetched = store.get(rule.key)
    assert fetched.target_spec == "make a flat list of names"
    assert fetched.target_kind == "description"
