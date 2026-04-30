import pytest

from translet import Translet, TransletConfig
from translet.store import DbSetStore

from ..conftest import FakeLLM


@pytest.fixture
def sqlite_store(tmp_path):
    from dbset import connect

    db = connect(f"sqlite:///{tmp_path / 'translet.db'}")
    store = DbSetStore(db, table="rules")
    yield store
    db.close()


def test_first_call_generates_second_call_hits_cache(sqlite_store):
    llm = FakeLLM(["{'name': user.name}"])
    t = Translet(llm=llm, store=sqlite_store)

    r1 = t.transjson.convert({"user": {"name": "Alice"}}, target_sample={"name": "x"})
    assert r1 == {"name": "Alice"}
    assert len(llm.calls) == 1

    r2 = t.transjson.convert({"user": {"name": "Bob"}}, target_sample={"name": "x"})
    assert r2 == {"name": "Bob"}
    assert len(llm.calls) == 1


def test_different_target_schemas_use_different_rules(sqlite_store):
    llm = FakeLLM(["{'value': user.age}", "{'value': user.name}"])
    t = Translet(llm=llm, store=sqlite_store)

    schema_int = {"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]}
    schema_str = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}

    r_int = t.transjson.convert({"user": {"name": "Alice", "age": 30}}, target_schema=schema_int)
    r_str = t.transjson.convert({"user": {"name": "Alice", "age": 30}}, target_schema=schema_str)
    assert r_int == {"value": 30}
    assert r_str == {"value": "Alice"}
    assert len(llm.calls) == 2


def test_named_rule_shared_across_payloads(sqlite_store):
    llm = FakeLLM(["{'name': user.name}"])
    t = Translet(llm=llm, store=sqlite_store)

    t.transjson.convert(
        {"user": {"name": "A"}, "completely": "different"},
        target_sample={"name": "x"},
        name="user_name_rule",
    )
    t.transjson.convert(
        {"user": {"name": "B"}, "totally": "other"},
        target_sample={"name": "x"},
        name="user_name_rule",
    )
    assert len(llm.calls) == 1


def test_invalidate_forces_regeneration(sqlite_store):
    llm = FakeLLM(["{'name': user.name}", "{'name': user.name}"])
    t = Translet(llm=llm, store=sqlite_store)

    t.transjson.convert(
        {"user": {"name": "A"}}, target_sample={"name": "x"}, name="my_rule"
    )
    t.transjson.invalidate("my_rule")
    t.transjson.convert(
        {"user": {"name": "B"}}, target_sample={"name": "x"}, name="my_rule"
    )
    assert len(llm.calls) == 2


def test_regenerate_after_validation_failure(sqlite_store):
    llm = FakeLLM(["user.name", "{'name': user.name}"])
    t = Translet(llm=llm, store=sqlite_store, config=TransletConfig(max_retries=2))

    result = t.transjson.convert(
        {"user": {"name": "A"}}, target_sample={"name": "x"}
    )
    assert result == {"name": "A"}
    assert len(llm.calls) == 2
