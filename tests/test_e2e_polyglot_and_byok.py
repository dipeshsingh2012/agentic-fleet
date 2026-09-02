"""
End-to-end tests for Polyglot workspace discovery and Multi-Provider BYOK orchestration.
Simulates autonomous SDLC pipelines on TypeScript and Go projects.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.event_router import EventRouter
from src.github_client import GitHubClient
from src.test_harness import TestHarness, TestResult


@pytest.mark.asyncio
async def test_e2e_typescript_repo_pipeline(tmp_path: Path):
    """Simulates a TypeScript project: verifies npm test runner selection and file materialization."""
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "frontend-app",
        "scripts": {"test": "vitest run"}
    }))
    (tmp_path / "src").mkdir(parents=True)
    (tmp_path / "src" / "api.ts").write_text("export function callApi() { return 200; }")

    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    executed_commands = []

    async def mock_run(cmd: str):
        executed_commands.append(cmd)
        return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="1 passed", stderr="")

    harness.run_command = AsyncMock(side_effect=mock_run)

    router = EventRouter(dry_run=False, test_harness=harness)
    router._get_workspace_dir = lambda: tmp_path

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.token = "token"
    mock_client.create_issue_comment = AsyncMock()
    mock_client.create_pull_request = AsyncMock(return_value={"number": 20, "html_url": "https://pr/20"})
    mock_client.add_labels = AsyncMock()
    mock_client.remove_label = AsyncMock()
    mock_client.find_existing_pr = AsyncMock(return_value=None)
    router.github_client = mock_client

    # Dev-agent produces TypeScript code
    ts_code = (
        "```typescript:src/auth.ts\nexport function login() { return true; }\n```\n"
        "```typescript:src/auth.test.ts\nimport { login } from './auth';\ntest('login', () => { expect(login()).toBe(true); });\n```"
    )
    router.llm_runner.generate_response = AsyncMock(return_value=ts_code)

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/web-app"},
        "issue": {"number": 20, "title": "Add Auth Service", "body": "Implement login"},
    }

    result = await router.handle_dev_agent("dipeshsingh2012/web-app", payload)

    assert result["agent"] == "dev-agent"
    assert (tmp_path / "src" / "auth.ts").exists()
    assert (tmp_path / "src" / "auth.test.ts").exists()
    # TypeScript repos must not have Python __init__.py package markers generated
    assert not (tmp_path / "src" / "__init__.py").exists()

    # Verify npm test was chosen as pre-commit verification command
    assert any("npm test" in cmd for cmd in executed_commands)


@pytest.mark.asyncio
async def test_e2e_go_repo_pipeline(tmp_path: Path):
    """Simulates a Go project: verifies go test runner selection and file materialization."""
    (tmp_path / "go.mod").write_text("module example.com/api\n\ngo 1.22\n")

    harness = MagicMock(spec=TestHarness)
    harness.cwd = str(tmp_path)
    executed_commands = []

    async def mock_run(cmd: str):
        executed_commands.append(cmd)
        return TestResult(command=cmd, exit_code=0, duration_seconds=0.1, stdout="ok  example.com/api 0.05s", stderr="")

    harness.run_command = AsyncMock(side_effect=mock_run)

    router = EventRouter(dry_run=False, test_harness=harness)
    router._get_workspace_dir = lambda: tmp_path

    mock_client = MagicMock(spec=GitHubClient)
    mock_client.token = "token"
    mock_client.create_issue_comment = AsyncMock()
    mock_client.create_pull_request = AsyncMock(return_value={"number": 25, "html_url": "https://pr/25"})
    mock_client.add_labels = AsyncMock()
    mock_client.remove_label = AsyncMock()
    mock_client.find_existing_pr = AsyncMock(return_value=None)
    router.github_client = mock_client

    go_code = (
        "```go:handler.go\npackage main\n\nfunc Handle() string { return \"ok\" }\n```\n"
        "```go:handler_test.go\npackage main\n\nimport \"testing\"\nfunc TestHandle(t *testing.T) {}\n```"
    )
    router.llm_runner.generate_response = AsyncMock(return_value=go_code)

    payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/go-service"},
        "issue": {"number": 25, "title": "Add Go Handler", "body": ""},
    }

    result = await router.handle_dev_agent("dipeshsingh2012/go-service", payload)

    assert result["agent"] == "dev-agent"
    assert (tmp_path / "handler.go").exists()
    assert (tmp_path / "handler_test.go").exists()
    assert not (tmp_path / "__init__.py").exists()

    # Verify go test runner was executed
    assert any("go test" in cmd for cmd in executed_commands)
