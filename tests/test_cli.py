from typer.testing import CliRunner
from src.cli import app

runner = CliRunner()


def test_cli_dry_run():
    result = runner.invoke(app, ["--dry-run", "--event-name", "issues", "--event-action", "opened"])
    assert result.exit_code == 0
    assert "Agentic Fleet Orchestrator" in result.stdout
    assert "pm-agent" in result.stdout


def test_cli_agent_override():
    result = runner.invoke(app, ["--dry-run", "--agent", "qa"])
    assert result.exit_code == 0
    assert "qa-agent" in result.stdout
