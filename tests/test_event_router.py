import pytest
from unittest.mock import AsyncMock, MagicMock
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
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["stages"]["security_agent"]["agent"] == "security-agent"
    assert result["stages"]["qa_agent"]["agent"] == "qa-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


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
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["stages"]["qa_agent"]["agent"] == "qa-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


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
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


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


def test_agent_context_builder(tmp_path):
    from src.event_router import AgentContextBuilder
    (tmp_path / "backend").mkdir()
    (tmp_path / "Taskfile.yml").write_text("version: 3\n")

    info = AgentContextBuilder.inspect_workspace(tmp_path)
    assert info["has_backend"] is True
    assert "Taskfile.yml" in info["key_configs"]

    block = AgentContextBuilder.format_context_block(
        workspace_info=info,
        issue_info={"number": 4, "title": "Add CSV Export", "body": "Need streaming export"},
        review_history="#### 💬 Review by @security-agent: Passed",
        test_summary={"total": 63, "passed": 63, "failed": 0, "duration": 1.5, "snippet": "63 passed"}
    )
    assert "Repository Architecture & Workspace Context" in block
    assert "Add CSV Export" in block
    assert "Review by @security-agent" in block
    assert "63 passed" in block


@pytest.mark.asyncio
async def test_route_review_failure_to_dev():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "submitted",
        "review": {"body": "## 🧪 QA Verification\nSTATUS: FAILED ❌\nAction Required for dev-agent"},
        "pull_request": {"number": 4},
        "repository": {"full_name": "owner/repo"}
    }
    result = await router.route_event("pull_request_review", payload)
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["stages"]["dev_agent"]["agent"] == "dev-agent"
    assert result["stages"]["security_agent"]["agent"] == "security-agent"
    assert result["stages"]["qa_agent"]["agent"] == "qa-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


@pytest.mark.asyncio
async def test_comment_mentioning_dev_agent_cascades_to_full_pipeline():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 21, "head": {"ref": "feat/21-fix"}, "labels": [{"name": "qa:failed"}]},
        "comment": {"body": "@dev-agent fix the issues raised by qa agent"},
    }

    result = await router.route_event("issue_comment", payload)

    assert result["stages"]["dev_agent"]["action"] == "remediated_pr"
    assert result["stages"]["security_agent"]["agent"] == "security-agent"
    assert result["stages"]["qa_agent"]["agent"] == "qa-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


@pytest.mark.asyncio
async def test_comment_mentioning_qa_agent_cascades_to_senior_reviewer_on_pass():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 22, "head": {"ref": "feat/22-qa"}, "labels": []},
        "comment": {"body": "@qa-agent verify"},
    }

    result = await router.route_event("issue_comment", payload)

    assert result["stages"]["pm_agent"]["status"] == "skipped"
    assert result["stages"]["dev_design"]["status"] == "skipped"
    assert result["stages"]["dev_agent"]["status"] == "skipped"
    assert result["stages"]["qa_agent"]["agent"] == "qa-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"
    assert result["status"] == "completed_awaiting_human_merge"


@pytest.mark.asyncio
async def test_pr_opened_event_cascades_through_security_qa_and_review():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "opened",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 23, "head": {"ref": "feat/23-opened"}, "labels": []},
    }

    result = await router.route_event("pull_request", payload)

    assert list(result["stages"]).index("security_agent") < list(result["stages"]).index("qa_agent")
    assert list(result["stages"]).index("qa_agent") < list(result["stages"]).index("senior_reviewer_agent")
    assert result["status"] == "completed_awaiting_human_merge"


@pytest.mark.asyncio
async def test_comment_mentioning_qa_agent_triggers_in_flight_dev_on_failure():
    router = EventRouter(dry_run=False)
    router._ensure_branch_checkout = AsyncMock()
    router.github_client = MagicMock()
    router.github_client.get_pull_request = AsyncMock(return_value={"head": {"ref": "feat/24-qa"}, "labels": []})
    router.github_client.get_pull_request_files = AsyncMock(return_value=[{"filename": "app/main.py"}])
    router.github_client.add_labels = AsyncMock()
    router.github_client.create_issue_comment = AsyncMock()
    router.github_client.get_pr_diff = AsyncMock(return_value="diff")
    router.github_client.get_pr_reviews = AsyncMock(return_value=[])
    router.github_client.get_issue_comments = AsyncMock(return_value=[])

    qa_results = iter([
        {"agent": "qa-agent", "action": "qa_verification", "response": "STATUS: FAILED ❌ test failure"},
        {"agent": "qa-agent", "action": "qa_verification", "response": "STATUS: PASSED ✅"},
    ])
    router.handle_security_agent = AsyncMock(return_value={"agent": "security-agent", "action": "security_audit", "response": "STATUS: PASSED ✅"})
    router.handle_qa_agent = AsyncMock(side_effect=lambda *args, **kwargs: next(qa_results))
    router.handle_dev_agent = AsyncMock(return_value={"agent": "dev-agent", "action": "remediated_pr", "pr_number": 24, "branch_name": "feat/24-qa"})
    router.handle_senior_reviewer_agent = AsyncMock(return_value={"agent": "senior-reviewer-agent", "action": "architect_review_approval", "verdict": "APPROVED"})

    payload = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "pull_request": {"number": 24, "head": {"ref": "feat/24-qa"}, "labels": []},
        "comment": {"body": "@qa-agent verify"},
    }

    result = await router.route_event("issue_comment", payload)

    assert router.handle_dev_agent.await_count == 1
    assert router.handle_qa_agent.await_count == 2
    assert result["stages"]["dev_agent"]["agent"] == "dev-agent"
    assert result["stages"]["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"
    assert result["status"] == "completed_awaiting_human_merge"


@pytest.mark.asyncio
async def test_route_untagged_human_comment_to_fleet():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "created",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {"number": 15, "title": "Implement Feature"},
        "comment": {
            "body": "Please make sure to add SSE transport support too.",
            "user": {"login": "dipeshsingh2012"},
        },
    }
    result = await router.route_event("issue_comment", payload)
    assert result["pipeline"] == "autonomous-5-agent-sdlc"


@pytest.mark.asyncio
async def test_ignore_bot_comments():
    router = EventRouter(dry_run=True)
    payload = {
        "action": "created",
        "repository": {"full_name": "dipeshsingh2012/rfqengine"},
        "issue": {"number": 15, "title": "Implement Feature"},
        "comment": {
            "body": "## 🚀 Autonomous 5-Agent SDLC Pipeline: Ready for Merge",
            "user": {"login": "github-actions[bot]"},
        },
    }
    result = await router.route_event("issue_comment", payload)
    assert result["status"] == "ignored"
    assert "bot user" in result["reason"]
