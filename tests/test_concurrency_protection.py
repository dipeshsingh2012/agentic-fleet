"""
Unit tests for optimistic git push rebase-retry and concurrency protection.
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.event_router import EventRouter
from src.github_client import GitHubClient
from src.test_harness import TestHarness, TestResult


@pytest.mark.asyncio
async def test_git_push_optimistic_rebase_retry(tmp_path: Path):
    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)

    push_count = 0

    async def dynamic_run_command(cmd: str):
        nonlocal push_count
        if "git push" in cmd:
            push_count += 1
            if push_count == 1:
                return TestResult(command=cmd, exit_code=1, duration_seconds=0.1, stdout="", stderr="rejected (non-fast-forward)")
            return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="Everything up-to-date", stderr="")
        return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="1 passed", stderr="")

    harness.run_command = AsyncMock(side_effect=dynamic_run_command)

    router = EventRouter(dry_run=False, test_harness=harness)
    mock_client = MagicMock(spec=GitHubClient)
    mock_client.token = "token"
    mock_client.create_issue_comment = AsyncMock()
    mock_client.create_pull_request = AsyncMock(return_value={"number": 42, "html_url": "https://pr/42"})
    mock_client.add_labels = AsyncMock()
    mock_client.remove_label = AsyncMock()
    mock_client.find_existing_pr = AsyncMock(return_value=None)
    router.github_client = mock_client

    router.llm_runner.generate_response = AsyncMock(
        return_value="```python:main.py\n# Code\n```"
    )

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {"number": 42, "title": "Concurrent Task", "body": ""},
    }

    result = await router.handle_dev_agent("dipeshsingh2012/rfpengine", payload)
    assert result["agent"] == "dev-agent"

    # Verify git fetch was invoked to recover from the failed push
    git_fetch_called = any("git fetch" in str(call) for call in harness.run_command.call_args_list)
    assert git_fetch_called
