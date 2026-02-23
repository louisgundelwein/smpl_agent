"""Tests for src.tools.github."""

import json

import httpx
import pytest
import respx

from src.tools.github import GitHubTool


@pytest.fixture
def tool():
    return GitHubTool(token="ghp_test123")


def test_name(tool):
    assert tool.name == "github"


def test_schema_structure(tool):
    schema = tool.schema
    assert schema["type"] == "function"
    func = schema["function"]
    assert func["name"] == "github"

    params = func["parameters"]
    assert "method" in params["properties"]
    assert "endpoint" in params["properties"]
    assert "body" in params["properties"]
    assert "params" in params["properties"]
    assert params["required"] == ["method", "endpoint"]


@respx.mock
def test_execute_get_success(tool):
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"login": "testuser", "id": 1})
    )

    result = json.loads(tool.execute(method="GET", endpoint="/user"))

    assert result["status_code"] == 200
    body = json.loads(result["body"])
    assert body["login"] == "testuser"


@respx.mock
def test_execute_post_success(tool):
    respx.post("https://api.github.com/repos/owner/repo/issues").mock(
        return_value=httpx.Response(
            201, json={"number": 42, "title": "Bug report"}
        )
    )

    result = json.loads(
        tool.execute(
            method="POST",
            endpoint="/repos/owner/repo/issues",
            body={"title": "Bug report", "body": "Something is broken"},
        )
    )

    assert result["status_code"] == 201
    body = json.loads(result["body"])
    assert body["number"] == 42


@respx.mock
def test_execute_with_params(tool):
    respx.get("https://api.github.com/repos/owner/repo/issues").mock(
        return_value=httpx.Response(200, json=[{"number": 1}, {"number": 2}])
    )

    result = json.loads(
        tool.execute(
            method="GET",
            endpoint="/repos/owner/repo/issues",
            params={"state": "open", "per_page": "10"},
        )
    )

    assert result["status_code"] == 200


def test_execute_missing_method(tool):
    result = json.loads(tool.execute(endpoint="/user"))

    assert "error" in result
    assert "method" in result["error"]


def test_execute_missing_endpoint(tool):
    result = json.loads(tool.execute(method="GET"))

    assert "error" in result
    assert "endpoint" in result["error"]


@respx.mock
def test_execute_http_error(tool):
    respx.get("https://api.github.com/repos/owner/nonexistent").mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    result = json.loads(
        tool.execute(method="GET", endpoint="/repos/owner/nonexistent")
    )

    assert result["status_code"] == 404
    assert "error" in result


@respx.mock
def test_execute_timeout(tool):
    respx.get("https://api.github.com/user").mock(
        side_effect=httpx.TimeoutException("Connection timed out")
    )

    result = json.loads(tool.execute(method="GET", endpoint="/user"))

    assert result["error"] == "Request timed out"


@respx.mock
def test_execute_auth_header(tool):
    route = respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"login": "testuser"})
    )

    tool.execute(method="GET", endpoint="/user")

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer ghp_test123"
    assert request.headers["Accept"] == "application/vnd.github+json"
    assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_execute_truncation():
    tool = GitHubTool(token="ghp_test123", max_output=2500)
    long_text = "x" * 5000

    truncated = tool._truncate(long_text)

    assert len(truncated) <= 2500
    assert "TRUNCATED" in truncated


@respx.mock
def test_execute_generic_exception(tool):
    respx.get("https://api.github.com/user").mock(
        side_effect=RuntimeError("unexpected error")
    )

    result = json.loads(tool.execute(method="GET", endpoint="/user"))

    assert "error" in result
    assert "unexpected error" in result["error"]


@respx.mock
def test_execute_no_content_204(tool):
    respx.delete("https://api.github.com/repos/owner/repo/issues/1/lock").mock(
        return_value=httpx.Response(204)
    )

    result = json.loads(
        tool.execute(
            method="DELETE", endpoint="/repos/owner/repo/issues/1/lock"
        )
    )

    assert result["status_code"] == 204
    assert result["body"] is None
