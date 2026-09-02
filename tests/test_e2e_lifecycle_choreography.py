"""
Comprehensive End-to-End (E2E) Flow Test Suite for Autonomous Agentic SDLC.
Validates state machine transitions, event webhooks, label handoffs, discrete defect halts,
and self-healing remediation cycles across all 5 role-bound agents.
"""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.event_router import EventRouter
from src.github_client import GitHubClient
from src.test_harness import TestHarness, TestResult


def create_mock_github_client() -> GitHubClient:
    """Helper to create a fully wired async mock GitHubClient."""
    client = MagicMock(spec=GitHubClient)
    client.token = "test-token"
    client.find_existing_pr = AsyncMock(return_value=None)
    client.get_issue = AsyncMock(return_value={"number": 1, "title": "Test Issue", "body": "Issue body", "labels": []})
    client.get_issue_comments = AsyncMock(return_value=[])
    client.get_pr_reviews = AsyncMock(return_value=[])
    client.get_pull_request = AsyncMock(return_value={"number": 1, "head": {"ref": "feat/1-test"}, "labels": []})
    client.get_pull_request_files = AsyncMock(return_value=[{"filename": "backend/app/main.py"}])
    client.get_pr_diff = AsyncMock(return_value="+ # changes\n")
    client.create_issue_comment = AsyncMock(return_value={"id": 100})
    client.create_pr_review = AsyncMock(return_value={"id": 200})
    client.create_pull_request = AsyncMock(return_value={"number": 1, "html_url": "https://github.com/test/pull/1"})
    client.add_labels = AsyncMock(return_value=[])
    client.remove_label = AsyncMock(return_value=[])
    client.merge_pull_request = AsyncMock(return_value={"merged": True})
    return client


@pytest.fixture
def mock_repo_workspace(tmp_path: Path):
    """Creates a realistic polyglot workspace with backend and test directories."""
    backend_dir = tmp_path / "backend" / "app"
    tests_dir = tmp_path / "backend" / "tests"
    docs_design = tmp_path / "docs" / "design"
    docs_adr = tmp_path / "docs" / "adr"
    backend_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    docs_design.mkdir(parents=True)
    docs_adr.mkdir(parents=True)

    (tmp_path / "pytest.ini").write_text("[pytest]\npythonpath = .\n")
    (tmp_path / "Taskfile.yml").write_text("version: 3\n")
    (backend_dir / "main.py").write_text("# FastAPI Main\n")
    (docs_adr / "ADR-001-architecture.md").write_text("# ADR 001: Standard Layout\n")
    return tmp_path


# ==============================================================================
# 1. HAPPY PATH: Greenfield Issue to Final Approval & Merge
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_happy_path_greenfield_to_merge(mock_repo_workspace: Path):
    """
    E2E Happy Path Journey:
    1. Human opens Issue #1.
    2. Autonomous pipeline runs: PM -> Dev Design -> Arch Gate 1 -> Dev Impl & PR -> Sec Gate 2 -> QA Gate 3 -> Senior Reviewer Gate 4.
    3. Final state is APPROVED & labeled ready-for-merge.
    4. Subsequent events on closed/merged PR are safely ignored by the merge guard.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=0, duration_seconds=0.1, stdout="32 passed", stderr="")
    )

    router = EventRouter(dry_run=True, test_harness=harness)

    # 1. Trigger Autonomous SDLC from newly opened issue
    issue_payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 1,
            "title": "Add Multi-Tenant RFP Export Pipeline",
            "body": "## User Story\nAs a user, I want to export RFPs partitioned by tenant_id.\n\n### Acceptance Criteria\n- Export to XLSX under 3s.",
            "labels": [],
        },
    }

    result = await router.route_event("issues", issue_payload)

    # Verify pipeline execution
    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["status"] == "completed_awaiting_human_merge"

    stages = result["stages"]
    assert stages["pm_agent"]["agent"] == "pm-agent"
    assert stages["dev_design"]["agent"] == "dev-agent"
    assert stages["architect_agent"]["agent"] == "architect-agent"
    assert stages["architect_agent"]["verdict"] == "DESIGN_APPROVED"
    assert stages["dev_agent"]["agent"] == "dev-agent"
    assert stages["security_agent"]["agent"] == "security-agent"
    assert stages["qa_agent"]["agent"] == "qa-agent"
    assert stages["senior_reviewer_agent"]["agent"] == "senior-reviewer-agent"

    # 2. Closed / Merged PR Guard: Verify merged PR webhook does not trigger duplicate runs
    merged_payload = {
        "action": "closed",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 1, "state": "closed", "merged": True, "title": "Add Multi-Tenant RFP Export"},
    }
    merged_res = await router.route_event("pull_request", merged_payload)
    assert merged_res["status"] == "ignored"
    assert "merged" in merged_res["reason"].lower()


# ==============================================================================
# 2. PM INTERACTIVE CLARIFICATION DIALOGUE
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_pm_clarification_cycle(mock_repo_workspace: Path):
    """
    Validates the 2-step interactive requirement clarification flow:
    Step 1: Vague one-liner issue halts pipeline with status:needs-clarification.
    Step 2: Human replies with option choices -> PM synthesizes Living PRD and tags agent:ready-for-design.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    router.github_client = mock_client

    # Step 1: Vague one-liner issue
    vague_payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 2, "title": "make search fast", "body": "", "labels": []},
        "force_clarify": True,
    }

    step1_res = await router.handle_pm_agent("dipeshsingh2012/rfpengine", vague_payload)
    assert step1_res["action"] == "clarification_requested"
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 2, ["status:needs-clarification"])

    # Step 2: Human comments with answers
    comment_payload = {
        "action": "created",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 2,
            "title": "make search fast",
            "labels": [{"name": "status:needs-clarification"}],
        },
        "comment": {
            "body": "Answers to PM Questionnaire:\n1A (PostgreSQL pgvector), 2B (Sub-200ms latency), 3A (Tenant filtered)",
            "user": {"login": "dipeshsingh2012"},
        },
    }

    step2_res = await router.handle_pm_agent("dipeshsingh2012/rfpengine", comment_payload)
    assert step2_res["agent"] == "pm-agent"
    assert step2_res["action"] == "formatted_spec"
    mock_client.remove_label.assert_called_with("dipeshsingh2012/rfpengine", 2, "status:needs-clarification")
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 2, ["agent:ready-for-design"])


# ==============================================================================
# 3. ARCHITECT DESIGN REJECTION & DISCRETE REMEDIATION
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_architect_design_rejection_and_revision(mock_repo_workspace: Path):
    """
    Validates Architect Gate 1 design rejection:
    Step 1: Architect rejects design -> applies status:changes-requested -> halts pipeline.
    Step 2: status:changes-requested on Issue routes to dev-design for doc revision.
    Step 3: Revised design submitted -> Architect approves -> tags agent:ready-for-dev.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    router.github_client = mock_client

    # Step 1: Architect rejects design
    router.llm_runner.generate_response = AsyncMock(
        return_value="STATUS: CHANGES_REQUESTED 🛑 ADR Violation: Missing data isolation model."
    )
    design_review_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 3, "title": "New Search Module", "labels": [{"name": "agent:design-review"}]},
    }
    arch_res = await router.handle_architect_agent("dipeshsingh2012/rfpengine", design_review_payload)
    assert arch_res["verdict"] == "CHANGES_REQUESTED"
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 3, ["status:changes-requested"])

    # Step 2: Issue status:changes-requested routes to dev-design
    remed_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 3, "title": "New Search Module", "labels": [{"name": "status:changes-requested"}]},
        "label": {"name": "status:changes-requested"},
    }
    dev_design_res = await router.route_event("issues", remed_payload)
    assert dev_design_res["agent"] == "dev-agent"
    assert dev_design_res["action"] == "design_authored"

    # Step 3: Architect re-audits and approves
    router.llm_runner.generate_response = AsyncMock(
        return_value="STATUS: APPROVED (LGTM ✅) Complies with all ADRs."
    )
    arch_approved_res = await router.handle_architect_agent("dipeshsingh2012/rfpengine", design_review_payload)
    assert arch_approved_res["verdict"] == "DESIGN_APPROVED"
    mock_client.add_labels.assert_called_with(
        "dipeshsingh2012/rfpengine", 3, ["agent:design-approved", "agent:ready-for-dev"]
    )


# ==============================================================================
# 4. SECURITY DEFECT DETECTION & DISCRETE DEV REMEDIATION
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_security_defect_and_discrete_remediation(mock_repo_workspace: Path):
    """
    Validates Security Gate 2:
    Step 1: Security flags SQL injection / raw queries -> applies security:blocked.
    Step 2: security:blocked triggers dev-agent remediation -> patches code -> applies ready-for-qa.
    Step 3: Security re-audit passes -> applies ready-for-qa.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=0, duration_seconds=0.1, stdout="passed", stderr="")
    )
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    mock_client.get_pr_diff = AsyncMock(return_value="+ query = f'SELECT * FROM rfps WHERE tenant={tenant}'")
    router.github_client = mock_client

    # Step 1: Security Agent flags defect
    router.llm_runner.generate_response = AsyncMock(
        return_value="STATUS: BLOCKED 🛑 Critical Finding: SQL injection in search query."
    )
    sec_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 10, "head": {"ref": "feat/10-search"}, "labels": [{"name": "ready-for-security-audit"}]},
    }
    sec_res = await router.handle_security_agent("dipeshsingh2012/rfpengine", sec_payload)
    assert sec_res["agent"] == "security-agent"
    assert "BLOCKED" in sec_res["response"]
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 10, ["security:blocked"])

    # Step 2: security:blocked label routes to dev-agent for remediation
    router.llm_runner.generate_response = AsyncMock(
        return_value="### Remediation\n```python:backend/app/query.py\ndef safe_query(tenant: str):\n    return db.query(RFP).filter_by(tenant=tenant).all()\n```"
    )
    blocked_event_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 10, "head": {"ref": "feat/10-search"}, "labels": [{"name": "security:blocked"}]},
        "label": {"name": "security:blocked"},
    }
    dev_remed_res = await router.route_event("pull_request", blocked_event_payload)
    assert dev_remed_res["agent"] == "dev-agent"
    assert dev_remed_res["action"] == "remediated_pr"
    mock_client.remove_label.assert_any_call("dipeshsingh2012/rfpengine", 10, "security:blocked")
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 10, ["ready-for-qa"])


# ==============================================================================
# 5. QA ADVERSARIAL FAILURE & DISCRETE DEV REMEDIATION
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_qa_adversarial_failure_and_remediation(mock_repo_workspace: Path):
    """
    Validates QA Gate 3:
    Step 1: QA test execution encounters failure on runner -> applies qa:failed & status:changes-requested -> halts.
    Step 2: qa:failed label routes to dev-agent -> dev fixes test -> clears defect labels -> applies ready-for-qa.
    Step 3: QA re-run passes -> applies qa:passed and ready-for-review.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    # Simulate failed pytest run on step 1
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=1, duration_seconds=0.2, stdout="", stderr="AssertionError: 500 != 200")
    )
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    mock_client.get_pr_diff = AsyncMock(return_value="+ def test_api(): assert 500 == 200")
    router.github_client = mock_client

    # Step 1: QA fails and applies defect labels
    router.llm_runner.generate_response = AsyncMock(
        return_value="STATUS: FAILED ❌ Test suite failed with AssertionError: 500 != 200"
    )
    qa_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 12, "head": {"ref": "feat/12-lint"}, "labels": [{"name": "ready-for-qa"}]},
    }
    qa_res = await router.handle_qa_agent("dipeshsingh2012/rfpengine", qa_payload)
    assert qa_res["agent"] == "qa-agent"
    assert "FAILED" in qa_res["response"]
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 12, ["qa:failed"])

    # Step 2: qa:failed label event triggers dev remediation
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=0, duration_seconds=0.1, stdout="1 passed", stderr="")
    )
    router.llm_runner.generate_response = AsyncMock(
        return_value="### Remediation\n```python:backend/tests/test_api.py\ndef test_api(): assert 200 == 200\n```"
    )
    qa_defect_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 12, "head": {"ref": "feat/12-lint"}, "labels": [{"name": "qa:failed"}]},
        "label": {"name": "qa:failed"},
    }
    dev_fix_res = await router.route_event("pull_request", qa_defect_payload)
    assert dev_fix_res["agent"] == "dev-agent"
    assert dev_fix_res["action"] == "remediated_pr"
    mock_client.remove_label.assert_any_call("dipeshsingh2012/rfpengine", 12, "qa:failed")
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 12, ["ready-for-qa"])

    # Step 3: QA re-run passes
    router.llm_runner.generate_response = AsyncMock(
        return_value="STATUS: PASSED ✅ All unit and adversarial tests passed."
    )
    qa_pass_res = await router.handle_qa_agent("dipeshsingh2012/rfpengine", qa_payload)
    assert qa_pass_res["agent"] == "qa-agent"
    assert "PASSED" in qa_pass_res["response"]
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 12, ["qa:passed", "ready-for-review"])


# ==============================================================================
# 6. SENIOR REVIEWER CHANGES REQUESTED & FINAL APPROVAL
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_senior_reviewer_changes_requested_and_approval(mock_repo_workspace: Path):
    """
    Validates Senior Reviewer Gate 4:
    Step 1: Senior reviewer requests changes -> creates review with REQUEST_CHANGES -> applies status:changes-requested.
    Step 2: Bot review with state 'changes_requested' passes bot filter and invokes dev-agent remediation.
    Step 3: Subsequent review approved -> creates review with APPROVE -> applies status:approved, ready-for-merge.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=0, duration_seconds=0.1, stdout="passed", stderr="")
    )
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    mock_client.get_pr_diff = AsyncMock(return_value="+ def export(): pass")
    router.github_client = mock_client

    # Step 1: Senior Reviewer requests changes
    router.llm_runner.generate_response = AsyncMock(
        return_value="DECISION: CHANGES_REQUESTED 🛑 Need docstrings and typed interfaces."
    )
    review_payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 15, "head": {"ref": "feat/15-export"}, "labels": [{"name": "ready-for-review"}]},
    }
    reviewer_res = await router.handle_senior_reviewer_agent("dipeshsingh2012/rfpengine", review_payload)
    assert reviewer_res["action"] == "architect_review_changes_requested"
    mock_client.create_pr_review.assert_called_with("dipeshsingh2012/rfpengine", 15, reviewer_res["response"], event="REQUEST_CHANGES")
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 15, ["status:changes-requested"])

    # Step 2: PR Review submitted by bot with changes_requested triggers dev remediation
    router.llm_runner.generate_response = AsyncMock(
        return_value="### Remediation\n```python:backend/app/export.py\ndef export() -> dict:\n    \"\"\"Typed docstring.\"\"\"\n    return {}\n```"
    )
    bot_review_event = {
        "action": "submitted",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 15, "head": {"ref": "feat/15-export"}},
        "review": {
            "state": "changes_requested",
            "body": "DECISION: CHANGES_REQUESTED 🛑 Need docstrings and typed interfaces.",
            "user": {"login": "github-actions[bot]"},
        },
    }
    dev_remed_res = await router.route_event("pull_request_review", bot_review_event)
    assert dev_remed_res["agent"] == "dev-agent"
    assert dev_remed_res["action"] == "remediated_pr"

    # Step 3: Final Approval
    router.llm_runner.generate_response = AsyncMock(
        return_value="DECISION: APPROVED (LGTM ✅) Architecture and code quality verified."
    )
    approved_res = await router.handle_senior_reviewer_agent("dipeshsingh2012/rfpengine", review_payload)
    assert approved_res["action"] == "architect_review_approval"
    mock_client.create_pr_review.assert_called_with("dipeshsingh2012/rfpengine", 15, approved_res["response"], event="APPROVE")
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 15, ["status:approved", "ready-for-merge"])


# ==============================================================================
# 7. RUNAWAY REMEDIATION LOOP BUDGET CAP
# ==============================================================================
@pytest.mark.asyncio
async def test_e2e_loop_budget_cap_protection(mock_repo_workspace: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Validates that if dev-agent fails to resolve defects after MAX_REMOTE_REMEDIATIONS (e.g. 2),
    it halts and applies status:manual-intervention-required instead of looping infinitely.
    """
    monkeypatch.setenv("MAX_REMOTE_REMEDIATIONS", "2")
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_repo_workspace)
    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = create_mock_github_client()
    mock_client.get_issue_comments = AsyncMock(
        return_value=[
            {"body": "## 🔄 `dev-agent` Remediation Update 1"},
            {"body": "## 🔄 `dev-agent` Remediation Update 2"},
        ]
    )
    router.github_client = mock_client

    payload = {
        "action": "labeled",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "pull_request": {"number": 22, "head": {"ref": "feat/22-stuck"}, "labels": [{"name": "qa:failed"}]},
        "label": {"name": "qa:failed"},
    }

    result = await router.route_event("pull_request", payload)
    assert result["agent"] == "dev-agent"
    assert result["action"] == "halted_budget_exceeded"
    mock_client.add_labels.assert_called_with("dipeshsingh2012/rfpengine", 22, ["status:manual-intervention-required"])
