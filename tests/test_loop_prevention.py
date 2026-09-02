"""
Loop Prevention & Termination Guarantee Test Suite.
Validates that autonomous agents, pre-commit self-healing loops, and webhook triggers
CANNOT get stuck in infinite recursion or execution loops.

Guarantees tested:
1. Dev Agent Pre-Commit Auto-Remediation Loop is strictly capped at max 3 iterations.
2. Bot-originated comments and PR reviews are strictly ignored to prevent CI ping-pong storms.
3. 5-Stage Autonomous SDLC Pipeline executes as an acyclic directed graph (DAG), never re-triggering itself.
4. Repeated failing tests gracefully terminate after iteration budget is exhausted.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.event_router import EventRouter
from src.test_harness import TestHarness, TestResult


@pytest.mark.asyncio
async def test_dev_agent_remediation_loop_strictly_capped_at_5_iterations(tmp_path: Path):
    """
    Ensures that if tests continuously fail, the dev agent's pre-commit auto-remediation loop
    strictly terminates after at most 5 iterations and does NOT loop indefinitely.
    """
    mock_harness = MagicMock(spec=TestHarness)
    mock_harness.cwd = str(tmp_path)

    call_counts = {"tests": 0, "git": 0}

    async def mock_run_command(cmd: str, timeout: float = 300.0) -> TestResult:
        if "pytest" in cmd:
            call_counts["tests"] += 1
            # Simulate persistent test failure
            return TestResult(
                command=cmd,
                exit_code=1,
                duration_seconds=0.5,
                stdout="FAILED tests/test_feature.py::test_case - AssertionError",
                stderr="",
                total_tests=10,
                passed_tests=9,
                failed_tests=1,
            )
        else:
            call_counts["git"] += 1
            return TestResult(
                command=cmd,
                exit_code=0,
                duration_seconds=0.1,
                stdout="success",
                stderr="",
            )

    mock_harness.run_command = AsyncMock(side_effect=mock_run_command)

    router = EventRouter(dry_run=False, test_harness=mock_harness)
    router.github_client = MagicMock()
    router.github_client.token = "mock-token"
    router.github_client.create_issue_comment = AsyncMock(return_value={"id": 101})
    router.github_client.create_pull_request = AsyncMock(return_value={"number": 42})
    router.github_client.add_issue_labels = AsyncMock(return_value={})

    # Prepare target workspace
    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 99,
            "title": "Add Broken Feature",
            "body": "This feature has a failing test",
            "labels": [{"name": "agent:ready-for-dev"}],
        },
    }

    result = await router.handle_dev_agent("dipeshsingh2012/rfpengine", payload)

    # STRICT ASSERTION: Exactly 5 test iterations were executed, no more, no less
    assert call_counts["tests"] == 5, f"Expected exactly 5 test iterations, but got {call_counts['tests']}"
    assert result["agent"] == "dev-agent"
    assert result["action"] == "toggled_development"


@pytest.mark.asyncio
async def test_dev_agent_remediation_env_override(tmp_path: Path, monkeypatch):
    """
    Ensures that MAX_REMEDIATION_ITERATIONS environment variable can configure the budget.
    """
    monkeypatch.setenv("MAX_REMEDIATION_ITERATIONS", "2")
    mock_harness = MagicMock(spec=TestHarness)
    mock_harness.cwd = str(tmp_path)

    call_counts = {"tests": 0}

    async def mock_run_command(cmd: str, timeout: float = 300.0) -> TestResult:
        if "pytest" in cmd:
            call_counts["tests"] += 1
            return TestResult(command=cmd, exit_code=1, duration_seconds=0.1, stdout="fail", stderr="", failed_tests=1)
        return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="ok", stderr="")

    mock_harness.run_command = AsyncMock(side_effect=mock_run_command)

    router = EventRouter(dry_run=False, test_harness=mock_harness)
    router.github_client = MagicMock()
    router.github_client.token = "mock-token"
    router.github_client.create_issue_comment = AsyncMock(return_value={"id": 101})
    router.github_client.create_pull_request = AsyncMock(return_value={"number": 42})
    router.github_client.add_issue_labels = AsyncMock(return_value={})

    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 99, "title": "Test", "body": "test", "labels": [{"name": "agent:ready-for-dev"}]},
    }

    await router.handle_dev_agent("dipeshsingh2012/rfpengine", payload)
    assert call_counts["tests"] == 2


@pytest.mark.asyncio
async def test_dev_agent_remediation_loop_breaks_early_on_success(tmp_path: Path):
    """
    Ensures that if tests fail on iteration 1 but succeed on iteration 2, the loop
    immediately breaks early and does NOT waste unnecessary iterations.
    """
    mock_harness = MagicMock(spec=TestHarness)
    mock_harness.cwd = str(tmp_path)

    call_counts = {"tests": 0}

    async def mock_run_command(cmd: str, timeout: float = 300.0) -> TestResult:
        if "pytest" in cmd:
            call_counts["tests"] += 1
            if call_counts["tests"] == 1:
                # Iteration 1: Failure
                return TestResult(
                    command=cmd,
                    exit_code=1,
                    duration_seconds=0.2,
                    stdout="FAILED test_something",
                    stderr="",
                    failed_tests=1,
                )
            else:
                # Iteration 2: Success!
                return TestResult(
                    command=cmd,
                    exit_code=0,
                    duration_seconds=0.2,
                    stdout="5 passed in 0.2s",
                    stderr="",
                    total_tests=5,
                    passed_tests=5,
                    failed_tests=0,
                )
        return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="ok", stderr="")

    mock_harness.run_command = AsyncMock(side_effect=mock_run_command)

    router = EventRouter(dry_run=False, test_harness=mock_harness)
    router.github_client = MagicMock()
    router.github_client.token = "mock-token"
    router.github_client.create_issue_comment = AsyncMock(return_value={"id": 102})
    router.github_client.create_pull_request = AsyncMock(return_value={"number": 43})
    router.github_client.add_issue_labels = AsyncMock(return_value={})

    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 100,
            "title": "Fix Flaky Feature",
            "body": "Fix on iteration 2",
            "labels": [{"name": "agent:ready-for-dev"}],
        },
    }

    result = await router.handle_dev_agent("dipeshsingh2012/rfpengine", payload)

    # STRICT ASSERTION: Broke immediately after iteration 2 passed
    assert call_counts["tests"] == 2, f"Expected exactly 2 iterations before break, but got {call_counts['tests']}"
    assert result["agent"] == "dev-agent"


@pytest.mark.asyncio
async def test_bot_comments_are_ignored_to_prevent_infinite_webhook_storms():
    """
    Ensures comments and reviews from bots (github-actions[bot], agentic-fleet, etc.)
    are immediately discarded so bots never trigger each other in a loop.
    """
    router = EventRouter(dry_run=True)

    bot_usernames = [
        "github-actions[bot]",
        "agentic-fleet",
        "dependabot[bot]",
        "codecov[bot]",
        "gemini-bot[bot]",
    ]

    for bot in bot_usernames:
        # 1. Issue Comment by Bot
        comment_payload = {
            "action": "created",
            "repository": {"full_name": "dipeshsingh2012/rfpengine"},
            "issue": {"number": 5},
            "comment": {
                "body": "## 🚀 Autonomous 5-Agent SDLC Pipeline: Ready for Merge\nPlease merge this PR.",
                "user": {"login": bot},
            },
        }
        res = await router.route_event("issue_comment", comment_payload)
        assert res["status"] == "ignored", f"Failed for issue comment by {bot}"
        assert "bot user" in res["reason"]

        # 2. PR Review Comment by Bot
        review_comment_payload = {
            "action": "created",
            "repository": {"full_name": "dipeshsingh2012/rfpengine"},
            "pull_request": {"number": 5},
            "comment": {
                "body": "Security Audit completed with 0 high findings.",
                "user": {"login": bot},
            },
        }
        res_review_comment = await router.route_event("pull_request_review_comment", review_comment_payload)
        assert res_review_comment["status"] == "ignored", f"Failed for PR review comment by {bot}"

        # 3. PR Review Submission by Bot
        review_payload = {
            "action": "submitted",
            "repository": {"full_name": "dipeshsingh2012/rfpengine"},
            "pull_request": {"number": 5},
            "review": {
                "body": "STATUS: PASSED 🛡️ All checks green.",
                "user": {"login": bot},
            },
        }
        res_review = await router.route_event("pull_request_review", review_payload)
        assert res_review["status"] == "ignored", f"Failed for PR review by {bot}"


@pytest.mark.asyncio
async def test_pipeline_execution_is_strictly_linear_and_acyclic(tmp_path: Path):
    """
    Validates that run_autonomous_pipeline runs as an acyclic graph through all 5 stages
    in exact order (1 -> 2 -> 3 -> 4 -> 5) and finishes with completed_awaiting_human_merge,
    never cycling back to stage 1.
    """
    harness = TestHarness(cwd=str(tmp_path))
    router = EventRouter(dry_run=True, test_harness=harness)
    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 55,
            "title": "Verify Linear Pipeline Execution",
            "body": "Acyclic test",
            "labels": [],
        },
    }

    result = await router.run_autonomous_pipeline("dipeshsingh2012/rfpengine", payload)

    # 1. Pipeline terminates cleanly
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["status"] == "completed_awaiting_human_merge"

    # 2. Stage keys are exactly the distinct roles, executed once each in acyclic sequence
    stage_keys = list(result["stages"].keys())
    assert stage_keys == [
        "pm_agent",
        "dev_design",
        "architect_agent",
        "dev_agent",
        "security_agent",
        "qa_agent",
        "senior_reviewer_agent",
    ]
