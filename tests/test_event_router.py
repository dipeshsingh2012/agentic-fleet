import pytest
from src.event_router import EventRouter


@pytest.mark.asyncio
async def test_route_issue_opened_to_pm():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {
            "number": 10,
            "title": "Add Excel ingestion",
            "body": "Need parser for large xlsx spreadsheets.",
            "labels": [{"name": "agent:pm"}],
        },
    }
    result = await router.route_event("issues", payload)
    assert result["agent"] == "pm-agent"
    assert result["action"] == "formatted_spec"
    assert result["issue_number"] == 10


@pytest.mark.asyncio
async def test_route_issue_labeled_to_dev():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {
            "number": 10,
            "title": "Add Excel ingestion",
            "body": "Spec approved.",
            "labels": [{"name": "agent:ready-for-dev"}],
        },
    }
    result = await router.route_event("issues", payload)
    assert result["agent"] == "dev-agent"
    assert result["action"] == "toggled_development"


@pytest.mark.asyncio
async def test_route_pr_opened_to_security():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "pull_request": {
            "number": 20,
            "title": "feat: excel ingestion",
            "labels": [],
        },
    }
    result = await router.route_event("pull_request", payload)
    assert result["agent"] == "security-agent"
    assert result["action"] == "security_audit"
    assert result["pr_number"] == 20


@pytest.mark.asyncio
async def test_route_pr_ready_for_qa():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "pull_request": {
            "number": 20,
            "title": "feat: excel ingestion",
            "labels": [{"name": "ready-for-qa"}],
        },
    }
    result = await router.route_event("pull_request", payload)
    assert result["agent"] == "qa-agent"
    assert result["action"] == "qa_verification"


@pytest.mark.asyncio
async def test_route_pr_ready_for_review():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "pull_request": {
            "number": 20,
            "title": "feat: excel ingestion",
            "labels": [{"name": "ready-for-review"}],
        },
    }
    result = await router.route_event("pull_request", payload)
    assert result["agent"] == "senior-reviewer-agent"
    assert result["action"] == "architect_review_approval"


@pytest.mark.asyncio
async def test_route_comment_mentions():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "created",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {"number": 15, "title": "Check Security"},
        "comment": {"body": "@security-agent please audit this endpoint"},
    }
    result = await router.route_event("issue_comment", payload)
    assert result["agent"] == "security-agent"


@pytest.mark.asyncio
async def test_route_autonomous_pipeline():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {
            "number": 12,
            "title": "Add Vector Filter",
            "body": "Need tenant-filtered vector search.",
            "labels": [{"name": "agent:autonomous"}],
        },
    }
    result = await router.route_event("issues", payload)
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert "pm_agent" in result["stages"]
    assert "dev_agent" in result["stages"]
    assert "security_agent" in result["stages"]
    assert "qa_agent" in result["stages"]
    assert "senior_reviewer_agent" in result["stages"]
    assert result["status"] == "completed_awaiting_human_merge"


def test_materialize_code_files(tmp_path):
    router = EventRouter(dry_run=True)
    content = """
Here is the implementation:

```python:app/services/calculator.py
def add(a, b):
    return a + b
```

```python:tests/test_calculator.py
from app.services.calculator import add
def test_add():
    assert add(1, 2) == 3
```
"""
    files = router._materialize_code_files(tmp_path, content)
    assert "app/services/calculator.py" in files
    assert "tests/test_calculator.py" in files
    assert (tmp_path / "app" / "services" / "calculator.py").exists()
    assert (tmp_path / "tests" / "test_calculator.py").exists()
    assert "def add(a, b):" in (tmp_path / "app" / "services" / "calculator.py").read_text()
