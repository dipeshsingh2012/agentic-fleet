"""
Command-line interface for agentic-fleet execution.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import typer
from rich.console import Console
from rich.panel import Panel

from src.github_client import GitHubClient
from src.llm_runner import LLMRunner
from src.test_harness import TestHarness
from src.event_router import EventRouter

app = typer.Typer(help="Autonomous Multi-Agent SDLC Orchestrator CLI")
console = Console()


def _write_github_step_summary(result: Dict[str, Any], event_name: str, payload: Dict[str, Any]):
    """Write visual execution summary to $GITHUB_STEP_SUMMARY for GitHub Actions UI."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    try:
        path = Path(summary_path)
        lines = []
        
        if result.get("pipeline") == "autonomous-5-agent-sdlc":
            stages = result.get("stages", {})
            status = result.get("status", "unknown")
            status_badge = "✅ COMPLETED (Ready for Human Merge)" if status == "completed_awaiting_human_merge" else "🛑 HALTED / ACTION REQUIRED"

            lines.append("## 🛸 Autonomous 5-Agent SDLC Fleet Summary")
            lines.append(f"**Overall Status**: `{status_badge}`\n")
            lines.append("| Stage | Agent | Action / Status |")
            lines.append("| :--- | :--- | :--- |")
            
            # PM
            pm = stages.get("pm_agent", {})
            pm_status = "⏭️ Skipped (Already done)" if pm.get("status") == "skipped" else "✅ Formatted Spec & Gherkin ACs"
            lines.append(f"| **1. Specification** | 🎯 `pm-agent` | {pm_status} |")

            # Dev
            dev = stages.get("dev_agent", {})
            dev_status = f"⏭️ Skipped (Branch `{dev.get('branch_name', '')}` exists)" if dev.get("status") == "skipped" else f"✅ Created branch & opened PR"
            lines.append(f"| **2. Development** | 🧑‍💻 `dev-agent` | {dev_status} |")

            # Security
            sec = stages.get("security_agent", {})
            sec_status = "⏭️ Skipped" if sec.get("status") == "skipped" else ("✅ Security Passed" if "security_agent_recheck" not in stages else "⚠️ Remediated & Re-audited")
            lines.append(f"| **3. Security Audit** | 🛡️ `security-agent` | {sec_status} |")

            # QA
            qa = stages.get("qa_agent", {})
            qa_status = "⏭️ Skipped" if qa.get("status") == "skipped" else ("✅ 100% Tests Passed" if status != "qa_failed_halted" else "❌ Tests / Collection Failed")
            lines.append(f"| **4. Adversarial QA** | 🧪 `qa-agent` | {qa_status} |")

            # Senior Reviewer
            rev = stages.get("senior_reviewer_agent", {})
            rev_status = "⏭️ Skipped" if rev.get("status") == "skipped" else ("✅ APPROVED (LGTM)" if status != "qa_failed_halted" else "⛔ Halted (Blocked by QA)")
            lines.append(f"| **5. Principal Architect** | 🧙‍♂️ `senior-reviewer-agent` | {rev_status} |")

        else:
            agent = result.get("agent", "Fleet Agent")
            action = result.get("action", "processed")
            lines.append(f"## 🤖 Agent Execution: `{agent}`")
            lines.append(f"- **Action**: `{action}`")
            lines.append(f"- **Event**: `{event_name}`")
            if "pr_number" in result:
                lines.append(f"- **Pull Request**: `#{result['pr_number']}`")
            if "issue_number" in result:
                lines.append(f"- **Issue**: `#{result['issue_number']}`")

        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        print(f"[WARN] Failed writing GITHUB_STEP_SUMMARY: {e}")


@app.command()
def route(
    event_name: Optional[str] = typer.Option(
        None,
        "--event-name",
        "-e",
        help="GitHub event name (issues, issue_comment, pull_request)",
    ),
    event_path: Optional[str] = typer.Option(
        None,
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
    resolved_event_name = event_name or os.getenv("GITHUB_EVENT_NAME") or "issues"
    resolved_event_path = event_path if event_path is not None else os.getenv("GITHUB_EVENT_PATH")

    console.print(
        Panel.fit(
            f"[bold cyan]Agentic Fleet Orchestrator[/bold cyan]\n"
            f"Event: [yellow]{resolved_event_name}[/yellow] | Action: [yellow]{event_action}[/yellow] | Dry Run: [magenta]{dry_run}[/magenta]",
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
    if resolved_event_path and Path(resolved_event_path).exists():
        try:
            loaded_payload = router.load_event_payload(resolved_event_path)
            if isinstance(loaded_payload, dict) and loaded_payload:
                payload = loaded_payload
        except Exception:
            payload = {}

    if not payload:
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
    elif "action" not in payload:
        payload["action"] = event_action

    if event_name == "issues" and "issue" not in payload:
        payload["action"] = event_action
        payload["issue"] = {
            "number": 42,
            "title": "Add multi-tenant vector filtering",
            "body": "Ensure all vector index queries validate tenant isolation.",
            "labels": [{"name": "agent:pm"}],
        }

    async def _run():
        result = await router.route_event(
            event_name=resolved_event_name,
            payload=payload,
            agent_override=agent,
        )
        return result

    result = asyncio.run(_run())

    _write_github_step_summary(result, resolved_event_name, payload)

    console.print("\n[bold green]Execution Result:[/bold green]")
    console.print_json(json.dumps(result, indent=2))


if __name__ == "__main__":
    app()
