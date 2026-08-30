"""
Command-line interface for agentic-fleet execution.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel

from src.github_client import GitHubClient
from src.llm_runner import LLMRunner
from src.test_harness import TestHarness
from src.event_router import EventRouter

app = typer.Typer(help="Autonomous Multi-Agent SDLC Orchestrator CLI")
console = Console()


@app.command()
def route(
    event_name: str = typer.Option(
        os.getenv("GITHUB_EVENT_NAME", "issues"),
        "--event-name",
        "-e",
        help="GitHub event name (issues, issue_comment, pull_request)",
    ),
    event_path: Optional[str] = typer.Option(
        os.getenv("GITHUB_EVENT_PATH"),
        "--event-path",
        "-p",
        help="Path to GitHub event JSON file",
    ),
    agent: Optional[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Explicit agent override (pm, dev, security, qa, senior-reviewer)",
    ),
    event_action: str = typer.Option(
        "opened",
        "--event-action",
        help="Fallback action if no event payload is supplied",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-d",
        help="Execute in simulation mode without making real GitHub or LLM API calls",
    ),
):
    """Route a GitHub action/webhook event to the appropriate autonomous agent."""
    console.print(
        Panel.fit(
            f"[bold cyan]Agentic Fleet Orchestrator[/bold cyan]\n"
            f"Event: [yellow]{event_name}[/yellow] | Action: [yellow]{event_action}[/yellow] | Dry Run: [magenta]{dry_run}[/magenta]",
            border_style="cyan",
        )
    )

    github_client = GitHubClient()
    llm_runner = LLMRunner()
    test_harness = TestHarness()
    router = EventRouter(
        github_client=github_client,
        llm_runner=llm_runner,
        test_harness=test_harness,
        dry_run=dry_run,
    )

    payload = {}
    if event_path and Path(event_path).exists():
        payload = router.load_event_payload(event_path)
    else:
        # Construct synthetic default payload for CLI testing
        payload = {
            "action": event_action,
            "repository": {"full_name": "dipeshsingh2012/rfqengine"},
            "issue": {
                "number": 42,
                "title": "Add multi-tenant vector filtering",
                "body": "Ensure all vector index queries validate tenant isolation.",
                "labels": [{"name": "agent:pm"}],
            },
            "pull_request": {
                "number": 25,
                "title": "feat: multi-tenant vector filtering",
                "labels": [{"name": "ready-for-qa"}],
            },
        }

    async def _run():
        result = await router.route_event(
            event_name=event_name,
            payload=payload,
            agent_override=agent,
        )
        return result

    result = asyncio.run(_run())

    console.print("\n[bold green]Execution Result:[/bold green]")
    console.print_json(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
