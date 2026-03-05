"""Tests for PlatformKnowledge."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.marketing.base import BrowserTask
from src.marketing.platform_knowledge import PlatformKnowledge


@pytest.fixture
def mock_db():
    """Mock Database with cursor context manager."""
    db = MagicMock()
    conn = MagicMock()
    db.get_connection.return_value = conn
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return db, conn, cursor


@pytest.fixture
def knowledge(mock_db, tmp_path):
    """PlatformKnowledge with mocked DB and temp guide dir."""
    db, _, _ = mock_db
    # Write a test guide
    guides_dir = tmp_path / "guides"
    guides_dir.mkdir()
    (guides_dir / "linkedin.md").write_text("# LinkedIn Guide\n\nTest guide content.")
    return PlatformKnowledge(knowledge_dir=guides_dir, db=db)


class TestGetGuide:
    def test_reads_existing_guide(self, knowledge):
        guide = knowledge.get_guide("linkedin")
        assert "LinkedIn Guide" in guide
        assert "Test guide content" in guide

    def test_returns_empty_for_missing_guide(self, knowledge):
        guide = knowledge.get_guide("tiktok")
        assert guide == ""


class TestGetLearnings:
    def test_get_all_learnings(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.fetchall.return_value = [
            {"key": "login_button", "value": "blue button top right", "confidence": 0.8},
            {"key": "feed_scroll", "value": "infinite scroll", "confidence": 0.6},
        ]
        result = knowledge.get_learnings("linkedin")
        assert "login_button" in result
        assert result["login_button"]["value"] == "blue button top right"
        assert result["login_button"]["confidence"] == 0.8

    def test_get_learnings_with_keys(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.fetchall.return_value = [
            {"key": "login_button", "value": "blue button", "confidence": 0.9},
        ]
        result = knowledge.get_learnings("linkedin", keys=["login_button"])
        assert "login_button" in result
        # Verify the query used IN clause
        call_args = cursor.execute.call_args
        assert "IN" in call_args[0][0]


class TestRecordLearning:
    def test_record_new_learning(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        knowledge.record_learning("linkedin", "new_key", "new_value", 0.7)
        cursor.execute.assert_called()
        call_args = cursor.execute.call_args
        assert "INSERT INTO platform_learnings" in call_args[0][0]
        assert "ON CONFLICT" in call_args[0][0]
        conn.commit.assert_called()

    def test_record_learning_rollback_on_error(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.execute.side_effect = Exception("DB error")
        with pytest.raises(Exception, match="DB error"):
            knowledge.record_learning("linkedin", "key", "value")
        conn.rollback.assert_called()


class TestEnhanceTask:
    def test_enhance_adds_learnings(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.fetchall.return_value = [
            {"key": "post_button", "value": "Click blue Post button", "confidence": 0.9},
        ]
        task = BrowserTask(task_description="Create a post", start_url="https://linkedin.com")
        enhanced = knowledge.enhance_task("linkedin", task, context_keys=["post_button"])
        assert "Create a post" in enhanced.task_description
        assert "post_button" in enhanced.task_description
        assert "Click blue Post button" in enhanced.task_description
        assert enhanced.start_url == "https://linkedin.com"

    def test_enhance_skips_low_confidence(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.fetchall.return_value = [
            {"key": "unreliable", "value": "maybe this", "confidence": 0.1},
        ]
        task = BrowserTask(task_description="Do something")
        enhanced = knowledge.enhance_task("linkedin", task)
        assert "unreliable" not in enhanced.task_description

    def test_enhance_no_learnings(self, knowledge, mock_db):
        _, conn, cursor = mock_db
        cursor.fetchall.return_value = []
        task = BrowserTask(task_description="Do something")
        enhanced = knowledge.enhance_task("linkedin", task)
        assert enhanced.task_description == "Do something"
