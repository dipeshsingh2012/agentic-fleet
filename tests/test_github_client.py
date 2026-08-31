import pytest
import httpx
from src.github_client import GitHubClient


@pytest.mark.asyncio
async def test_github_client_init():
    client = GitHubClient(token="mock-token")
    assert client.token == "mock-token"
    assert "Bearer mock-token" in client.headers["Authorization"]


@pytest.mark.asyncio
async def test_get_issue(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_get(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"number": 12, "title": "Test Issue", "state": "open"}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    issue = await client.get_issue("owner/repo", 12)
    assert issue["number"] == 12
    assert issue["title"] == "Test Issue"


@pytest.mark.asyncio
async def test_create_issue_comment(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_post(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 201
            def raise_for_status(self): pass
            def json(self): return {"id": 101, "body": "Test comment"}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    comment = await client.create_issue_comment("owner/repo", 12, "Test comment")
    assert comment["id"] == 101
    assert comment["body"] == "Test comment"


@pytest.mark.asyncio
async def test_add_labels(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_post(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return [{"name": "agent:ready-for-dev"}]
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    labels = await client.add_labels("owner/repo", 12, ["agent:ready-for-dev"])
    assert len(labels) == 1
    assert labels[0]["name"] == "agent:ready-for-dev"


@pytest.mark.asyncio
async def test_get_pull_request(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_get(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"number": 25, "state": "open", "title": "feat: test"}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    pr = await client.get_pull_request("owner/repo", 25)
    assert pr["number"] == 25
    assert pr["title"] == "feat: test"


@pytest.mark.asyncio
async def test_create_pr_review(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_post(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"id": 501, "state": "APPROVED"}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    review = await client.create_pr_review("owner/repo", 25, "LGTM", event="APPROVE")
    assert review["state"] == "APPROVED"


@pytest.mark.asyncio
async def test_merge_pull_request(monkeypatch):
    client = GitHubClient(token="mock-token")

    async def mock_put(self, url, *args, **kwargs):
        class MockResponse:
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"sha": "abc1234", "merged": True, "message": "Pull Request successfully merged"}
        return MockResponse()

    monkeypatch.setattr(httpx.AsyncClient, "put", mock_put)

    res = await client.merge_pull_request("owner/repo", 25)
    assert res["merged"] is True
