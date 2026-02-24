"""Tests for src.repos — repository registry store."""

import sqlite3

import pytest

from src.repos import RepoStore


@pytest.fixture
def store():
    """RepoStore backed by in-memory SQLite."""
    return RepoStore(db_path=":memory:")


def _add_sample(store: RepoStore, name: str = "smpl_agent") -> int:
    return store.add(
        name=name,
        owner="louisgundelwein",
        repo=name,
        url=f"https://github.com/louisgundelwein/{name}.git",
        default_branch="main",
        description="Test repo",
        tags=["python", "agent"],
    )


class TestAdd:
    def test_returns_id(self, store):
        repo_id = _add_sample(store)
        assert repo_id == 1

    def test_increments_ids(self, store):
        id1 = _add_sample(store, "repo1")
        id2 = _add_sample(store, "repo2")
        assert id2 > id1

    def test_duplicate_name_raises(self, store):
        _add_sample(store)
        with pytest.raises(sqlite3.IntegrityError):
            _add_sample(store)

    def test_default_values(self, store):
        store.add(name="minimal", owner="owner", repo="repo", url="https://example.com")
        repo = store.get("minimal")
        assert repo["default_branch"] == "main"
        assert repo["description"] == ""
        assert repo["tags"] == []


class TestListAll:
    def test_empty(self, store):
        assert store.list_all() == []

    def test_returns_all_sorted_by_name(self, store):
        _add_sample(store, "zeta")
        _add_sample(store, "alpha")
        repos = store.list_all()
        assert len(repos) == 2
        assert repos[0]["name"] == "alpha"
        assert repos[1]["name"] == "zeta"

    def test_tags_parsed(self, store):
        _add_sample(store)
        repos = store.list_all()
        assert repos[0]["tags"] == ["python", "agent"]


class TestGet:
    def test_found(self, store):
        _add_sample(store)
        repo = store.get("smpl_agent")
        assert repo is not None
        assert repo["owner"] == "louisgundelwein"
        assert repo["url"] == "https://github.com/louisgundelwein/smpl_agent.git"

    def test_not_found(self, store):
        assert store.get("nonexistent") is None


class TestRemove:
    def test_removes_existing(self, store):
        _add_sample(store)
        assert store.remove("smpl_agent") is True
        assert store.get("smpl_agent") is None

    def test_returns_false_for_missing(self, store):
        assert store.remove("nonexistent") is False


class TestUpdate:
    def test_updates_description(self, store):
        _add_sample(store)
        assert store.update("smpl_agent", description="Updated desc") is True
        repo = store.get("smpl_agent")
        assert repo["description"] == "Updated desc"

    def test_updates_tags_from_list(self, store):
        _add_sample(store)
        store.update("smpl_agent", tags=["new", "tags"])
        repo = store.get("smpl_agent")
        assert repo["tags"] == ["new", "tags"]

    def test_updates_default_branch(self, store):
        _add_sample(store)
        store.update("smpl_agent", default_branch="develop")
        repo = store.get("smpl_agent")
        assert repo["default_branch"] == "develop"

    def test_ignores_unknown_fields(self, store):
        _add_sample(store)
        assert store.update("smpl_agent", unknown_field="value") is False

    def test_returns_false_for_missing(self, store):
        assert store.update("nonexistent", description="x") is False


class TestCount:
    def test_empty(self, store):
        assert store.count() == 0

    def test_after_add(self, store):
        _add_sample(store)
        assert store.count() == 1

    def test_after_remove(self, store):
        _add_sample(store)
        store.remove("smpl_agent")
        assert store.count() == 0
