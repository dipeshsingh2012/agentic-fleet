"""
Unit tests for dev-agent automated dependency detection, manifest auto-installation,
and test collection error auto-remediation.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.event_router import EventRouter
from src.github_client import GitHubClient
from src.test_harness import TestHarness, TestResult


@pytest.fixture
def mock_workspace(tmp_path: Path):
    backend_dir = tmp_path / "backend" / "app"
    tests_dir = tmp_path / "backend" / "tests"
    backend_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi\npytest\n")
    return tmp_path


@pytest.mark.asyncio
async def test_dev_agent_auto_installs_materialized_requirements(mock_workspace: Path):
    """
    Verifies that when dev-agent outputs an updated requirements.txt,
    the event router automatically invokes `pip install -r requirements.txt` in the sandbox.
    """
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(mock_workspace)
    harness.run_command = AsyncMock(
        return_value=TestResult(command="pytest", exit_code=0, duration_seconds=0.1, stdout="1 passed", stderr="")
    )

    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.token = "fake-token"
    mock_client.create_issue_comment = AsyncMock()
    mock_client.create_pull_request = AsyncMock(return_value={"number": 20, "html_url": "https://github.com/pr/20"})
    mock_client.add_labels = AsyncMock()
    mock_client.remove_label = AsyncMock()
    mock_client.find_existing_pr = AsyncMock(return_value=None)
    router.github_client = mock_client

    # dev-agent outputs updated requirements.txt and source code
    router.llm_runner.generate_response = AsyncMock(
        return_value=(
            "```text:backend/requirements.txt\nfastapi\npytest\nPyJWT>=2.8.0\nemail-validator>=2.2.0\n```\n\n"
            "```python:backend/app/auth.py\nimport jwt\n```"
        )
    )

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 20, "title": "Implement JWT Auth", "body": "Add JWT auth"},
    }

    result = await router.handle_dev_agent("dipeshsingh2012/rfpengine", payload)

    assert result["agent"] == "dev-agent"
    assert result["action"] in ["toggled_development", "created_pr"]

    # Verify pip install was called on the materialized requirements.txt
    pip_install_called = any(
        "pip install -r" in call.args[0] for call in harness.run_command.call_args_list
    )
    assert pip_install_called, "Expected pip install -r to be executed when requirements.txt was updated"
