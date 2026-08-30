import os
from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_dry_run(monkeypatch):
    # Ensure test is isolated from external CI environment variables
    monkeypatch.setenv("GITHUB_EVENT_NAME", "issues")
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    result = runner.invoke(app, ["--dry-run", "--event-name", "issues", "--event-action", "opened"])
    assert result.exit_code == 0
    assert "Agentic Fleet Orchestrator" in result.stdout
    assert "pm-agent" in result.stdout


def test_cli_agent_override(monkeypatch):
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)

    result = runner.invoke(app, ["--dry-run", "--agent", "qa"])
    assert result.exit_code == 0
    assert "qa-agent" in result.stdout
