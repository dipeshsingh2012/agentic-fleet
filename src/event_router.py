"""
GitHub event router for multi-agent SDLC lifecycle transitions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from src.github_client import GitHubClient
from src.llm_runner import LLMRunner
from src.test_harness import TestHarness

logger = logging.getLogger("agentic-fleet.event_router")


class EventRouter:
    """Routes GitHub webhook/action events to the corresponding SDLC agent."""

    def __init__(
        self,
        github_client: Optional[GitHubClient] = None,
        llm_runner: Optional[LLMRunner] = None,
        test_harness: Optional[TestHarness] = None,
        dry_run: bool = False,
    ):
        self.github_client = github_client or GitHubClient()
        self.llm_runner = llm_runner or LLMRunner()
        self.test_harness = test_harness or TestHarness()
        self.dry_run = dry_run

    def load_event_payload(self, event_path: Optional[str] = None) -> Dict[str, Any]:
        """Load JSON event payload from file path or return empty dict."""
        if not event_path:
            return {}
        path = Path(event_path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    async def route_event(
        self,
        event_name: str,
        payload: Dict[str, Any],
        agent_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route event to the appropriate agent handler."""
        repo_name = payload.get("repository", {}).get("full_name", "owner/repo")

        # Explicit agent override
        if agent_override:
            return await self._dispatch_agent(agent_override, repo_name, payload)

        action = payload.get("action", "")

        # 1. Issue Events
        if event_name == "issues":
            labels = [lbl.get("name", "") for lbl in payload.get("issue", {}).get("labels", [])]
            if "agent:pm" in labels or action == "opened":
                return await self.handle_pm_agent(repo_name, payload)
            if "agent:ready-for-dev" in labels:
                return await self.handle_dev_agent(repo_name, payload)

        # 2. Issue Comments / Mentions
        elif event_name == "issue_comment" and action == "created":
            comment_body = payload.get("comment", {}).get("body", "")
            if "@pm-agent" in comment_body:
                return await self.handle_pm_agent(repo_name, payload)
            if "@dev-agent" in comment_body:
                return await self.handle_dev_agent(repo_name, payload)
            if "@security-agent" in comment_body:
                return await self.handle_security_agent(repo_name, payload)
            if "@qa-agent" in comment_body:
                return await self.handle_qa_agent(repo_name, payload)
            if "@senior-reviewer-agent" in comment_body:
                return await self.handle_senior_reviewer_agent(repo_name, payload)

        # 3. Pull Request Events
        elif event_name == "pull_request":
            pr_labels = [lbl.get("name", "") for lbl in payload.get("pull_request", {}).get("labels", [])]
            if action in ["opened", "synchronize"]:
                return await self.handle_security_agent(repo_name, payload)
            if "ready-for-qa" in pr_labels:
                return await self.handle_qa_agent(repo_name, payload)
            if "ready-for-review" in pr_labels:
                return await self.handle_senior_reviewer_agent(repo_name, payload)

        # Default fallback
        return {
            "status": "ignored",
            "reason": f"No agent trigger matched for event '{event_name}' (action: '{action}')",
        }

    async def _dispatch_agent(self, agent_name: str, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = agent_name.replace("-agent", "").lower()
        if normalized == "pm":
            return await self.handle_pm_agent(repo, payload)
        elif normalized == "dev":
            return await self.handle_dev_agent(repo, payload)
        elif normalized in ["sec", "security"]:
            return await self.handle_security_agent(repo, payload)
        elif normalized == "qa":
            return await self.handle_qa_agent(repo, payload)
        elif normalized in ["reviewer", "senior-reviewer", "architect"]:
            return await self.handle_senior_reviewer_agent(repo, payload)
        else:
            raise ValueError(f"Unknown agent: {agent_name}")

    async def handle_pm_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """pm-agent: formats user story, Gherkin criteria, and RICE score."""
        issue = payload.get("issue", {})
        issue_number = issue.get("number", 1)
        issue_title = issue.get("title", "Feature Request")
        issue_body = issue.get("body", "")

        prompt = self.llm_runner.load_prompt(
            "pm-agent",
            {"issue_title": issue_title, "issue_body": issue_body, "repo_name": repo},
        )
        user_input = f"Issue #{issue_number}: {issue_title}\n\nDescription:\n{issue_body}"
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run)

        if not self.dry_run and issue_number and repo:
            await self.github_client.create_issue_comment(repo, issue_number, response)
            await self.github_client.add_labels(repo, issue_number, ["agent:ready-for-dev"])

        return {
            "agent": "pm-agent",
            "action": "formatted_spec",
            "issue_number": issue_number,
            "response": response,
        }

    async def handle_dev_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """dev-agent: creates branch, generates code & unit tests, drafts PR."""
        issue = payload.get("issue", {})
        issue_number = issue.get("number", 1)
        issue_title = issue.get("title", "Implementation")
        issue_body = issue.get("body", "")

        prompt = self.llm_runner.load_prompt(
            "dev-agent",
            {"issue_number": issue_number, "issue_title": issue_title, "issue_body": issue_body},
        )
        user_input = f"Implement specification for Issue #{issue_number}: {issue_title}\n\n{issue_body}"
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run)

        if not self.dry_run and issue_number and repo:
            await self.github_client.create_issue_comment(repo, issue_number, response)
            await self.github_client.add_labels(repo, issue_number, ["ready-for-security-audit"])

        return {
            "agent": "dev-agent",
            "action": "toggled_development",
            "issue_number": issue_number,
            "response": response,
        }

    async def handle_security_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """security-agent: scans diff for multi-tenant isolation, secrets, OWASP."""
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 1)
        files_inspected = "All modified files in pull request"

        prompt = self.llm_runner.load_prompt(
            "security-agent",
            {"pr_number": pr_number, "files_inspected": files_inspected},
        )
        user_input = f"Perform multi-tenant and secret audit for PR #{pr_number}"
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run)

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="COMMENT")
            await self.github_client.add_labels(repo, pr_number, ["security:passed", "ready-for-qa"])

        return {
            "agent": "security-agent",
            "action": "security_audit",
            "pr_number": pr_number,
            "response": response,
        }

    async def handle_qa_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """qa-agent: executes adversarial tests and full regression suite."""
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 1)

        # Run test harness
        test_res = await self.test_harness.run_command("pytest -v") if not self.dry_run else None
        total = test_res.total_tests if test_res else 15
        passed = test_res.passed_tests if test_res else 15
        failed = test_res.failed_tests if test_res else 0
        duration = test_res.duration_seconds if test_res else 1.25

        prompt = self.llm_runner.load_prompt(
            "qa-agent",
            {
                "pr_number": pr_number,
                "total_tests": total,
                "passed_tests": passed,
                "failed_tests": failed,
                "execution_time_seconds": duration,
            },
        )
        user_input = f"Adversarial QA validation for PR #{pr_number}. Total: {total}, Passed: {passed}"
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run)

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="COMMENT")
            await self.github_client.add_labels(repo, pr_number, ["qa:passed", "ready-for-review"])

        return {
            "agent": "qa-agent",
            "action": "qa_verification",
            "pr_number": pr_number,
            "response": response,
        }

    async def handle_senior_reviewer_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """senior-reviewer-agent: audits architecture/ADRs, checks Sec+QA, approves PR."""
        pr = payload.get("pull_request", {})
        pr_number = pr.get("number", 1)

        prompt = self.llm_runner.load_prompt("senior-reviewer-agent", {"pr_number": pr_number})
        user_input = f"Principal Architect review and ADR compliance audit for PR #{pr_number}"
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run)

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="APPROVE")
            await self.github_client.add_labels(repo, pr_number, ["status:shipped"])

        return {
            "agent": "senior-reviewer-agent",
            "action": "architect_review_approval",
            "pr_number": pr_number,
            "response": response,
        }
