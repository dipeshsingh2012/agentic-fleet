"""
Full-Lifecycle SDLC Test Suite:
Validates:
1. PM Agent interactive clarification on vague/one-liner issues.
2. PM Agent PRD generation upon receiving user replies.
3. Dev Agent Phase 1: Technical Design Document authoring (docs/design/DESIGN-<id>.md).
4. Architect Agent Gate 1: Pre-implementation design review against ADRs.
5. Dev Agent Phase 2: Code materialization & pre-commit test sandbox.
6. Full 6-Stage Autonomous SDLC Pipeline execution.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.event_router import EventRouter
from src.test_harness import TestHarness, TestResult


@pytest.mark.asyncio
async def test_pm_agent_clarification_on_vague_issue(tmp_path: Path):
    """
    Validates that a vague/one-liner issue triggers the PM agent's
    Interactive Clarification Questionnaire and halts the pipeline.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 7,
            "title": "add export",
            "body": "",
            "labels": [],
        },
        "force_clarify": True,
    }

    # Test direct handle_pm_agent invocation
    pm_res = await router.handle_pm_agent("dipeshsingh2012/rfpengine", payload)
    assert pm_res["agent"] == "pm-agent"
    assert pm_res["action"] == "clarification_requested"
    assert pm_res["issue_number"] == 7

    # Test pipeline halts on clarification needed
    pipeline_res = await router.run_autonomous_pipeline("dipeshsingh2012/rfpengine", payload)
    assert pipeline_res["status"] == "awaiting_clarification"
    assert pipeline_res["stages"]["pm_agent"]["action"] == "clarification_requested"


@pytest.mark.asyncio
async def test_pm_agent_handles_human_clarification_reply(tmp_path: Path):
    """
    Validates that when a human replies to the questionnaire (e.g. '1A, 2A, 3A'),
    the PM agent synthesizes the full Living PRD and Gherkin scenarios.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)

    payload = {
        "action": "created",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 7,
            "title": "add export",
            "body": "1A, 2A, 3A: Streaming CSV export with tenant filtering",
            "labels": [{"name": "status:needs-clarification"}],
        },
        "comment": {
            "body": "1A, 2A, 3A: Please proceed with streaming CSV export and tenant header filtering",
            "user": {"login": "lead-engineer"},
        },
    }

    result = await router.handle_pm_agent("dipeshsingh2012/rfpengine", payload)

    assert result["agent"] == "pm-agent"
    assert result["action"] == "formatted_spec"
    assert result["issue_number"] == 7


@pytest.mark.asyncio
async def test_dev_agent_authors_technical_design_document(tmp_path: Path):
    """
    Validates that dev-agent (Phase 1) creates docs/design/DESIGN-<id>.md
    with component architecture, file impact, and test strategy.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)

    import os
    os.environ["TARGET_WORKSPACE"] = str(tmp_path)

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 8,
            "title": "Hybrid BM25 and Vector Search",
            "body": "Implement reciprocal rank fusion for dense and sparse search.",
            "labels": [{"name": "agent:ready-for-design"}],
        },
    }

    result = await router.handle_dev_design("dipeshsingh2012/rfpengine", payload)

    assert result["agent"] == "dev-agent"
    assert result["action"] == "design_authored"
    assert result["issue_number"] == 8

    # Verify physical file existence in docs/design/
    design_files = list((tmp_path / "docs" / "design").glob("DESIGN-8*.md"))
    assert len(design_files) == 1


@pytest.mark.asyncio
async def test_architect_agent_reviews_and_approves_design_doc(tmp_path: Path):
    """
    Validates that architect-agent audits the design doc against ADRs
    and emits DESIGN_APPROVED verdict.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)

    import os
    os.environ["TARGET_WORKSPACE"] = str(tmp_path)

    # Create dummy design doc
    design_dir = tmp_path / "docs" / "design"
    design_dir.mkdir(parents=True, exist_ok=True)
    design_file = design_dir / "DESIGN-8-hybrid-search.md"
    design_file.write_text("# Technical Design: Hybrid Search\n\n- Uses Reciprocal Rank Fusion\n- Strict X-Tenant-ID header filtering\n- backend/tests/test_hybrid_search.py unit tests")

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 8,
            "title": "Hybrid Search",
            "body": "Design ready for review",
            "labels": [{"name": "agent:design-review"}],
        },
    }

    result = await router.handle_architect_agent("dipeshsingh2012/rfpengine", payload)

    assert result["agent"] == "architect-agent"
    assert result["action"] == "design_reviewed"
    assert result["verdict"] == "DESIGN_APPROVED"


@pytest.mark.asyncio
async def test_full_6_stage_autonomous_sdlc_pipeline(tmp_path: Path):
    """
    Tests the complete 6-stage autonomous SDLC cascade:
    1. PM Agent (PRD)
    2. Dev Agent (Design Doc)
    3. Architect Agent (Design Gate)
    4. Dev Agent (Code Implementation & Sandbox Testing)
    5. Security & QA Agents (Verification)
    6. Senior Reviewer Agent (PR Merge Sign-Off)
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    harness.run_command = AsyncMock(return_value=TestResult(command="", exit_code=0, duration_seconds=0.1, stdout="ok", stderr=""))
    (tmp_path / "backend" / "tests").mkdir(parents=True, exist_ok=True)

    import os
    os.environ["TARGET_WORKSPACE"] = str(tmp_path)

    router = EventRouter(dry_run=True, test_harness=harness)

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 9,
            "title": "Add Excel Ingestion Service",
            "body": "Detailed specification: Parse multi-tab .xlsx files into chunks with sheet metadata and tenant isolation.",
            "labels": [],
        },
    }

    result = await router.run_autonomous_pipeline("dipeshsingh2012/rfpengine", payload)

    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["status"] == "completed_awaiting_human_merge"

    # Verify all 6 stages executed
    stages = result["stages"]
    assert "pm_agent" in stages
    assert "dev_design" in stages
    assert "architect_agent" in stages
    assert "dev_agent" in stages
    assert "security_agent" in stages
    assert "qa_agent" in stages
    assert "senior_reviewer_agent" in stages

    assert stages["dev_design"]["action"] == "design_authored"
    assert stages["architect_agent"]["verdict"] == "DESIGN_APPROVED"
    assert stages["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"


@pytest.mark.asyncio
async def test_architect_changes_requested_triggers_dev_design_revision(tmp_path: Path):
    """
    Validates that when the architect requests changes, the Dev Agent
    automatically receives feedback, updates docs/design/DESIGN-<id>.md,
    and resubmits for architect re-audit.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)

    import os
    os.environ["TARGET_WORKSPACE"] = str(tmp_path)

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 10,
            "title": "Token Bucket Rate Limiter",
            "body": "Design with token bucket",
            "labels": [{"name": "agent:design-review"}],
        },
        "architect_feedback": "Please add Redis cluster failover strategy and 429 Retry-After headers in Section 5.",
    }

    dev_rev_res = await router.handle_dev_design("dipeshsingh2012/rfpengine", payload)
    assert dev_rev_res["agent"] == "dev-agent"
    assert dev_rev_res["action"] == "design_authored"
    assert dev_rev_res["issue_number"] == 10

    # Verify updated design file created
    design_files = list((tmp_path / "docs" / "design").glob("DESIGN-10*.md"))
    assert len(design_files) == 1
