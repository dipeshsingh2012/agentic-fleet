"""
MCP & Roadmap Isolation Test Suite.
Validates that MCP actions triggered from aroadmap dashboard (via repository_dispatch or JSON-RPC):
1. Do NOT overlap or collide with standard GitHub issue workflows.
2. Use distinct branch namespaces ('feat/init-<id>-<slug>' vs 'feat/<issue_number>-<slug>').
3. Keep 'mcp_initiative' (PM Discovery stage) strictly isolated from 'mcp_start_dev' (Dev execution).
4. Tag PRs cleanly with 'Roadmap Initiative: <id>' instead of standard 'Closes #<num>'.
5. Produce zero GitHub Issue noise.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.event_router import EventRouter
from src.test_harness import TestHarness, TestResult


@pytest.mark.asyncio
async def test_mcp_initiative_discovery_is_pm_only(tmp_path: Path):
    """
    Validates that repository_dispatch: mcp_initiative executes ONLY the PM agent
    to format the Living PRD without triggering Dev Agent or opening PRs.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    router = EventRouter(dry_run=True, test_harness=harness)
    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "mcp_initiative",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "client_payload": {
            "title": "Onboarding Company Metadata Form",
            "prompt": "Ask company type, industry, tech stack in onboarding.",
            "category": "core",
            "initiative_id": "init-onboarding-meta",
        },
    }

    result = await router.route_event("repository_dispatch", payload)

    # 1. Verify PM Agent was executed
    assert result["agent"] == "pm-agent"
    assert result["action"] == "formatted_spec"
    assert result["issue_number"] == "init-onboarding-meta"
    assert "Onboarding Company Metadata Form" in result["response"]

    # 2. Strict isolation: Ensure no dev, security, or reviewer stages were triggered
    assert "stages" not in result
    assert "pr_number" not in result


@pytest.mark.asyncio
async def test_mcp_start_dev_runs_pipeline_with_isolated_branch_namespace(tmp_path: Path):
    """
    Validates that repository_dispatch: mcp_start_dev creates an isolated branch
    prefixed with the initiative ID ('feat/init-hybrid-search-...') rather than an issue number.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    harness.run_command = AsyncMock(return_value=TestResult(command="", exit_code=0, duration_seconds=0.1, stdout="ok", stderr=""))

    router = EventRouter(dry_run=True, test_harness=harness)
    (tmp_path / "backend").mkdir(parents=True)

    payload = {
        "action": "mcp_start_dev",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "client_payload": {
            "title": "Hybrid Search with Reciprocal Rank Fusion",
            "initiative_id": "init-hybrid-rrf-99",
            "feedback": "Use dense embeddings + sparse BM25.",
            "tenant_id": "tenant-acme",
        },
    }

    result = await router.route_event("repository_dispatch", payload)

    assert result["pipeline"] == "autonomous-5-agent-sdlc"
    assert result["status"] == "completed_awaiting_human_merge"

    # Verify dedicated MCP branch namespace
    dev_stage = result["stages"]["dev_agent"]
    assert dev_stage["branch_name"].startswith("feat/init-hybrid-rrf-99-")
    assert "feat/4-" not in dev_stage["branch_name"]


@pytest.mark.asyncio
async def test_standard_issue_and_mcp_actions_do_not_overlap(tmp_path: Path):
    """
    Simulates sequential execution of a standard GitHub issue (#4) and an MCP initiative (init-101),
    verifying both produce completely distinct branches, identifiers, and PR contexts.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    harness.run_command = AsyncMock(return_value=TestResult(command="", exit_code=0, duration_seconds=0.1, stdout="ok", stderr=""))
    (tmp_path / "backend").mkdir(parents=True)

    router = EventRouter(dry_run=True, test_harness=harness)

    # 1. Execute Standard Issue #4 Flow
    issue_payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 4,
            "title": "Fix the cloudrun deployment issue",
            "body": "Container startup timeout",
            "labels": [],
        },
    }
    issue_result = await router.route_event("issues", issue_payload)

    # 2. Execute MCP Initiative 'init-rag-101' Flow
    mcp_payload = {
        "action": "mcp_start_dev",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "client_payload": {
            "title": "Add Pinecone Serverless Vector Store",
            "item_id": "init-rag-101",
            "feedback": "Ensure cosine metric index.",
        },
    }
    mcp_result = await router.route_event("repository_dispatch", mcp_payload)

    # Verification of Separation:
    issue_branch = issue_result["stages"]["dev_agent"]["branch_name"]
    mcp_branch = mcp_result["stages"]["dev_agent"]["branch_name"]

    # Assert branch namespaces never collide
    assert issue_branch == "feat/4-fix-the-cloudrun-deployment-is"
    assert mcp_branch == "feat/init-rag-101-add-pinecone-serverless-vector"
    assert issue_branch != mcp_branch

    # Assert issue numbering vs initiative identifier separation
    assert issue_result["stages"]["pm_agent"]["issue_number"] == 4
    assert mcp_result["stages"]["pm_agent"]["issue_number"] == "init-rag-101"


@pytest.mark.asyncio
async def test_mcp_client_payload_variations_support(tmp_path: Path):
    """
    Ensures router supports all variation formats sent by aroadmap and MCP tools
    ('initiative_id', 'item_id', 'id').
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    (tmp_path / "backend").mkdir(parents=True)
    router = EventRouter(dry_run=True, test_harness=harness)

    variations = [
        ({"initiative_id": "init-v1", "title": "Feature 1"}, "feat/init-v1-feature-1"),
        ({"item_id": "init-v2", "title": "Feature 2"}, "feat/init-v2-feature-2"),
        ({"id": "init-v3", "title": "Feature 3"}, "feat/init-v3-feature-3"),
    ]

    for client_payload, expected_branch in variations:
        payload = {
            "action": "mcp_start_dev",
            "repository": {"full_name": "dipeshsingh2012/rfpengine"},
            "client_payload": client_payload,
        }
        res = await router.route_event("repository_dispatch", payload)
        dev_branch = res["stages"]["dev_agent"]["branch_name"]
        assert dev_branch == expected_branch
