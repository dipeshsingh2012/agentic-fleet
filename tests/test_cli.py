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

    assert "completed_awaiting_human_merge" in result.stdout


def test_cli_init_command(tmp_path: Path):
    result = runner.invoke(app, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0
    workflow = tmp_path / ".github" / "workflows" / "agentic-sdlc.yml"
    assert workflow.exists()
    content = workflow.read_text(encoding="utf-8")
    assert "Autonomous Agentic SDLC" in content
    assert "uses: dipeshsingh2012/agentic-fleet@v1" in content
    assert "gemini-api-key" in content
