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
