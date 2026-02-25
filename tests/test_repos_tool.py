"""Tests for src.tools.repos — repos tool."""

import json

import pytest

from src.repos import RepoStore
from src.tools.repos import ReposTool


@pytest.fixture
def store():
    """Fake RepoStore backed by an in-memory dict (no DB required)."""
    from unittest.mock import MagicMock
    s = MagicMock(spec=RepoStore)
    _data = {}
    _seq = iter(range(1, 10_000))

    def _add(name, owner, repo, url, default_branch="main", description="", tags=None):
        if name in _data:
            import psycopg2.errors
            raise psycopg2.errors.UniqueViolation("duplicate key")
        repo_id = next(_seq)
        _data[name] = dict(id=repo_id, name=name, owner=owner, repo=repo, url=url,
                           default_branch=default_branch, description=description,
                           tags=tags or [], added_at="2026-01-01T00:00:00+00:00")
        return repo_id

    def _update(name, **fields):
        if name not in _data:
            return False
        _data[name].update(fields)
        return True

    s.add.side_effect = _add
    s.list_all.side_effect = lambda: list(_data.values())
    s.get.side_effect = lambda name: _data.get(name)
    s.remove.side_effect = lambda name: bool(_data.pop(name, None))
    s.update.side_effect = _update
    s.count.side_effect = lambda: len(_data)
    return s


@pytest.fixture
def tool(store):
    return ReposTool(store=store)


def test_name(tool):
    assert tool.name == "repos"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "repos"
    props = func["parameters"]["properties"]
    assert "action" in props
    assert "name" in props
    assert "owner" in props
    assert func["parameters"]["required"] == ["action"]


class TestAddAction:
    def test_success(self, tool, store):
        result = json.loads(tool.execute(
            action="add",
            name="smpl_agent",
            owner="louisgundelwein",
            repo="smpl_agent",
            url="https://github.com/louisgundelwein/smpl_agent.git",
        ))
        assert result["added"] is True
        assert result["repo_id"] == 1
        assert result["total_repos"] == 1

    def test_with_optional_fields(self, tool, store):
        result = json.loads(tool.execute(
            action="add",
            name="myrepo",
            owner="me",
            repo="myrepo",
            url="https://github.com/me/myrepo.git",
            default_branch="develop",
            description="My project",
            tags=["python"],
        ))
        assert result["added"] is True

        repo = store.get("myrepo")
        assert repo["default_branch"] == "develop"
        assert repo["description"] == "My project"
        assert repo["tags"] == ["python"]

    def test_missing_fields(self, tool):
        result = json.loads(tool.execute(action="add", name="test"))
        assert "error" in result

    def test_duplicate_name(self, tool):
        tool.execute(
            action="add", name="r", owner="o", repo="r",
            url="https://example.com",
        )
        result = json.loads(tool.execute(
            action="add", name="r", owner="o", repo="r",
            url="https://example.com",
        ))
        assert "error" in result


class TestListAction:
    def test_empty(self, tool):
        result = json.loads(tool.execute(action="list"))
        assert result["repos"] == []
        assert result["count"] == 0

    def test_with_repos(self, tool):
        tool.execute(
            action="add", name="r1", owner="o", repo="r1",
            url="https://example.com/r1",
        )
        tool.execute(
            action="add", name="r2", owner="o", repo="r2",
            url="https://example.com/r2",
        )
        result = json.loads(tool.execute(action="list"))
        assert result["count"] == 2


class TestRemoveAction:
    def test_success(self, tool):
        tool.execute(
            action="add", name="r", owner="o", repo="r",
            url="https://example.com",
        )
        result = json.loads(tool.execute(action="remove", name="r"))
        assert result["removed"] is True

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="remove"))
        assert "error" in result

    def test_not_found(self, tool):
        result = json.loads(tool.execute(action="remove", name="nope"))
        assert result["removed"] is False


class TestGetAction:
    def test_found(self, tool):
        tool.execute(
            action="add", name="r", owner="myorg", repo="myrepo",
            url="https://github.com/myorg/myrepo.git",
        )
        result = json.loads(tool.execute(action="get", name="r"))
        assert result["repo"]["owner"] == "myorg"

    def test_not_found(self, tool):
        result = json.loads(tool.execute(action="get", name="nope"))
        assert "error" in result

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="get"))
        assert "error" in result


class TestUpdateAction:
    def test_updates_description(self, tool, store):
        tool.execute(
            action="add", name="r", owner="o", repo="r",
            url="https://example.com",
        )
        result = json.loads(tool.execute(
            action="update", name="r", description="New desc",
        ))
        assert result["updated"] is True
        assert store.get("r")["description"] == "New desc"

    def test_no_fields(self, tool):
        result = json.loads(tool.execute(action="update", name="r"))
        assert "error" in result

    def test_missing_name(self, tool):
        result = json.loads(tool.execute(action="update", description="x"))
        assert "error" in result


class TestUnknownAction:
    def test_returns_error(self, tool):
        result = json.loads(tool.execute(action="frobnicate"))
        assert "error" in result
