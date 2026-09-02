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

import json
from pathlib import Path

def test_cli_issue_opened_with_null_body(tmp_path: Path, monkeypatch):
    """Regression test ensuring CLI handles GitHub issue payload with body=null without error."""
    event_file = tmp_path / "event.json"
    event_payload = {
        "action": "opened",
        "repository": {"full_name": "dipeshsingh2012/rfpengine"},
        "issue": {
            "number": 4,
            "title": "Fix the cloudrun deployment issue",
            "body": None,
            "labels": [],
        },
    }
    event_file.write_text(json.dumps(event_payload), encoding="utf-8")
    monkeypatch.setenv("TARGET_WORKSPACE", str(tmp_path))

    result = runner.invoke(app, [
        "--dry-run",
        "--event-name", "issues",
        "--event-path", str(event_file),
    ])

    assert result.exit_code == 0
    assert "Agentic Fleet Orchestrator" in result.stdout
    assert "pm-agent" in result.stdout
    assert "dev-agent" in result.stdout
    assert "senior-reviewer-agent" in result.stdout
    assert "completed_awaiting_human_merge" in result.stdout
