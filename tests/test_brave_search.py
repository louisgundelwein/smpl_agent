"""Tests for src.tools.brave_search."""

import json

import httpx
import pytest
import respx

from src.tools.brave_search import BraveSearchTool


@pytest.fixture
def tool():
    return BraveSearchTool(api_key="test-key")


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "brave_web_search"
    assert "query" in schema["function"]["parameters"]["properties"]
    assert "query" in schema["function"]["parameters"]["required"]


@respx.mock
def test_execute_success(tool):
    respx.get(BraveSearchTool.ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        {
                            "title": "Test Result",
                            "url": "https://example.com",
                            "description": "A test result",
                        }
                    ]
                }
            },
        )
    )

    result = json.loads(tool.execute(query="test"))

    assert len(result["results"]) == 1
    assert result["results"][0]["title"] == "Test Result"
    assert result["results"][0]["url"] == "https://example.com"


@respx.mock
def test_execute_no_results(tool):
    respx.get(BraveSearchTool.ENDPOINT).mock(
        return_value=httpx.Response(200, json={"web": {"results": []}})
    )

    result = json.loads(tool.execute(query="nothing"))

    assert result["message"] == "No results found."
    assert result["results"] == []


@respx.mock
def test_execute_http_error(tool):
    respx.get(BraveSearchTool.ENDPOINT).mock(
        return_value=httpx.Response(500)
    )

    with pytest.raises(httpx.HTTPStatusError):
        tool.execute(query="fail")


def test_cooldown_enforced(mocker):
    tool = BraveSearchTool(api_key="test-key")

    mock_monotonic = mocker.patch("src.tools.brave_search.time.monotonic")
    mock_sleep = mocker.patch("src.tools.brave_search.time.sleep")

    # First call: _last_request_time=0, monotonic returns large value -> no sleep
    # After request: monotonic returns 100.0 (stored as _last_request_time)
    # Second call: monotonic returns 100.3 -> elapsed=0.3 < 1.0 -> sleep(0.7)
    # After request: monotonic returns 101.0
    mock_monotonic.side_effect = [
        100.0,   # first _enforce_cooldown: elapsed = 100.0 - 0.0 = huge, no sleep
        100.0,   # first request done, stored as _last_request_time
        100.3,   # second _enforce_cooldown: elapsed = 100.3 - 100.0 = 0.3 < 1.0
        101.0,   # second request done
    ]

    with respx.mock:
        respx.get(BraveSearchTool.ENDPOINT).mock(
            return_value=httpx.Response(200, json={"web": {"results": []}})
        )
        tool.execute(query="first")
        tool.execute(query="second")

    mock_sleep.assert_called_once()
    sleep_duration = mock_sleep.call_args[0][0]
    assert 0.6 < sleep_duration < 0.8
