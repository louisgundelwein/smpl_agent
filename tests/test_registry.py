"""Tests for src.tools.registry."""

import pytest


def test_register_and_get_schemas(empty_registry, dummy_tool):
    empty_registry.register(dummy_tool)
    schemas = empty_registry.get_schemas()

    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "dummy"


def test_register_duplicate_raises(empty_registry, dummy_tool):
    empty_registry.register(dummy_tool)

    with pytest.raises(ValueError, match="already registered"):
        empty_registry.register(dummy_tool)


def test_execute_dispatches_correctly(empty_registry, dummy_tool):
    empty_registry.register(dummy_tool)

    result = empty_registry.execute("dummy", arg1="hello")

    assert result == "dummy result: hello"


def test_execute_unknown_tool_raises(empty_registry):
    with pytest.raises(KeyError, match="Unknown tool"):
        empty_registry.execute("nonexistent")


def test_tool_names_property(empty_registry, dummy_tool):
    assert empty_registry.tool_names == []

    empty_registry.register(dummy_tool)

    assert empty_registry.tool_names == ["dummy"]
