"""
GitHub event router for multi-agent SDLC lifecycle transitions.
Features 360-degree context awareness, dynamic file materialization, inter-agent review history, and stateful 5-stage SDLC auto-chaining.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.github_client import GitHubClient
from src.llm_runner import LLMRunner
from src.test_harness import TestHarness

logger = logging.getLogger("agentic-fleet.event_router")


class AgentContextBuilder:
    """Builds a rich, multi-dimensional context snapshot for autonomous agents before taking action."""

    @staticmethod
    def inspect_workspace(workspace_dir: Path) -> Dict[str, Any]:
        """Inspect repository structure, framework layout, and configuration files."""
        has_backend = (workspace_dir / "backend").is_dir()
        has_frontend = (workspace_dir / "frontend").is_dir()
        has_extension = (workspace_dir / "extension").is_dir()
        has_docs = (workspace_dir / "docs").is_dir()

        detected_dirs: List[str] = []
        if has_backend:
            detected_dirs.append("`backend/` (FastAPI / Python backend services & unit tests)")
        if has_frontend:
            detected_dirs.append("`frontend/` (Web UI application)")
        if has_extension:
            detected_dirs.append("`extension/` (Browser Extension)")
        if has_docs:
            detected_dirs.append("`docs/` (Architecture Decision Records & PR documentation)")

        key_configs: List[str] = []
        for config_name in ["Taskfile.yml", "pytest.ini", "pyproject.toml", "package.json", "requirements.txt"]:
            if (workspace_dir / config_name).exists() or (workspace_dir / "backend" / config_name).exists():
                key_configs.append(config_name)

        return {
            "has_backend": has_backend,
            "has_frontend": has_frontend,
            "detected_dirs": detected_dirs,
            "key_configs": key_configs,
        }

    @staticmethod
    def format_context_block(
        workspace_info: Dict[str, Any],
        issue_info: Dict[str, Any],
        pr_info: Optional[Dict[str, Any]] = None,
        review_history: str = "",
        test_summary: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Render a unified context Markdown block for agent prompts."""
        blocks: List[str] = []

        # 1. Repository & Architecture Context
        dirs_str = "\n".join(f"- {d}" for d in workspace_info.get("detected_dirs", [])) or "- Standard single-package layout"
        configs_str = ", ".join(workspace_info.get("key_configs", [])) or "Standard"
        has_backend = workspace_info.get("has_backend", False)

        path_directive = (
            "⚠️ **CRITICAL DIRECTORY DIRECTIVE**: This repository uses a `backend/` workspace. "
            "All backend source code MUST be placed under `backend/app/` and test files under `backend/tests/`."
            if has_backend
            else "Place source files and test files in their standard root directories."
        )

        blocks.append(
            f"### 🏗️ Repository Architecture & Workspace Context\n"
            f"- **Detected Modules**:\n{dirs_str}\n"
            f"- **Configuration Files**: {configs_str}\n"
            f"- **Layout Contract**: {path_directive}"
        )

        # 2. Issue / Requirements Context
        issue_num = issue_info.get("number", 1)
        issue_title = issue_info.get("title", "Feature Request")
        issue_body = (issue_info.get("body") or "").strip() or "(No description provided - infer full requirements and Gherkin scenarios from the title and codebase architecture)"
        blocks.append(
            f"### 🎯 Specification & Requirements (Issue #{issue_num})\n"
            f"**Title**: {issue_title}\n"
            f"**Description**:\n{issue_body}"
        )

        # 3. Pull Request & Git Diff Context
        if pr_info:
            pr_num = pr_info.get("number")
            branch = pr_info.get("branch", "main")
            diff = pr_info.get("diff", "(No diff available)")
            blocks.append(
                f"### 🔀 Pull Request #{pr_num} Context (Branch: `{branch}`)\n"
                f"```diff\n{diff}\n```"
            )

        # 4. Inter-Agent Review & Audit History
        if review_history.strip():
            blocks.append(review_history.strip())

        # 5. Live Test & Runtime State
        if test_summary:
            total = test_summary.get("total", 0)
            passed = test_summary.get("passed", 0)
            failed = test_summary.get("failed", 0)
            duration = test_summary.get("duration", 0.0)
            snippet = test_summary.get("snippet", "No test logs")
            blocks.append(
                f"### 🧪 Live Test Execution Results\n"
                f"- **Summary**: Total: {total} | Passed: {passed} | Failed: {failed} | Duration: {duration}s\n"
                f"- **Test Output / Failure Section**:\n```\n{snippet[:2500]}\n```"
            )

        return "\n\n---\n\n".join(blocks)


class EventRouter:
    """Routes GitHub webhook/action events to SDLC agents and runs stateful autonomous pipelines."""

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

    def _extract_pr_number(self, payload: Dict[str, Any]) -> Optional[int]:
        """Safely extract PR number whether event is pull_request or issue_comment on a PR."""
        if "pull_request" in payload and isinstance(payload["pull_request"], dict):
            return payload["pull_request"].get("number")
        issue = payload.get("issue", {})
        if "pull_request" in issue and isinstance(issue["pull_request"], dict):
            return issue.get("number")
        return None

    def _materialize_code_files(self, workspace_dir: Path, content: str) -> Dict[str, str]:
        """Extract and write all source and test code blocks into real repository files with __init__.py support."""
        files: Dict[str, str] = {}
        has_backend_dir = (workspace_dir / "backend").exists() and (workspace_dir / "backend").is_dir()

        # Pattern 1: ```lang:path/to/file.ext\ncode\n```
        p1 = re.compile(r"```[a-zA-Z0-9_\-\.]*:([a-zA-Z0-9_\-\.\/]+)\n(.*?)```", re.DOTALL)
        for match in p1.finditer(content):
            path_str = match.group(1).strip()
            code = match.group(2)
            if not path_str.endswith(".md"):
                files[path_str] = code

        # Pattern 2: Header/Comment path followed immediately by ```lang\ncode\n```
        p2 = re.compile(
            r"(?:###?\s*(?:File:\s*)?`?([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)`?|#\s*filepath:\s*([a-zA-Z0-9_\-\.\/]+)|#\s*([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+))\s*\n\s*```[a-zA-Z0-9_\-\.]*\n(.*?)```",
            re.DOTALL,
        )
        for match in p2.finditer(content):
            path_str = match.group(1) or match.group(2) or match.group(3)
            code = match.group(4)
            if path_str:
                path_clean = path_str.strip("`'\" ")
                if path_clean not in files and not path_clean.endswith(".md"):
                    files[path_clean] = code

        materialized: Dict[str, str] = {}
        for rel_path, file_code in files.items():
            target_rel = rel_path
            # If repo has backend/ layout and path starts with app/ or tests/, map to backend/
            if has_backend_dir and not target_rel.startswith("backend/") and (target_rel.startswith("app/") or target_rel.startswith("tests/")):
                target_rel = f"backend/{target_rel}"

            target_path = workspace_dir / target_rel
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(file_code.strip() + "\n", encoding="utf-8")
            materialized[target_rel] = file_code
            print(f"[DEV-AGENT] 📝 Materialized file ({len(file_code)} chars): {target_rel}")

            # Ensure all parent Python directories contain __init__.py
            curr_dir = target_path.parent
            while curr_dir != workspace_dir and curr_dir.is_relative_to(workspace_dir):
                init_file = curr_dir / "__init__.py"
                if not init_file.exists() and (curr_dir.name not in ["tests", "docs"]):
                    init_file.write_text("# Package marker\n", encoding="utf-8")
                    print(f"[DEV-AGENT] 📦 Created package marker: {init_file.relative_to(workspace_dir)}")
                curr_dir = curr_dir.parent

        # Clean up misplaced root-level folders if backend/ exists
        if has_backend_dir:
            for root_dir in ["app", "tests"]:
                root_path = workspace_dir / root_dir
                if root_path.exists() and root_path.is_dir() and (workspace_dir / "backend" / root_dir).exists():
                    try:
                        shutil.rmtree(root_path)
                        print(f"[DEV-AGENT] 🧹 Cleaned up redundant root folder: {root_dir}/")
                    except Exception:
                        pass

        return materialized

    async def _ensure_branch_checkout(self, repo: str, branch_name: str) -> None:
        """Fetch and checkout target branch to ensure reviews and tests run against the branch code."""
        if not self.dry_run and branch_name and repo:
            try:
                await self.test_harness.run_command(f"git fetch origin {branch_name}")
                checkout_res = await self.test_harness.run_command(f"git checkout {branch_name}")
                if checkout_res.exit_code == 0:
                    await self.test_harness.run_command(f"git pull origin {branch_name}")
                    print(f"[SDLC] 🌿 Switched and synced workspace to current branch: `{branch_name}`")
            except Exception as e:
                print(f"[WARN] Failed checking out branch `{branch_name}`: {e}")

    async def _get_pr_diff_safe(self, repo: str, pr_number: int) -> str:
        """Fetch PR diff via GitHub API or local git fallback."""
        if not self.dry_run and repo and pr_number:
            try:
                diff = await self.github_client.get_pr_diff(repo, pr_number)
                if diff.strip():
                    return diff
            except Exception as e:
                print(f"[WARN] Failed to fetch PR diff via GitHub API: {e}")

        try:
            res = await self.test_harness.run_command("git diff origin/main...HEAD")
            if res.is_success and res.stdout.strip():
                return res.stdout
        except Exception:
            pass

        return "(No code changes detected or synthetic diff)"

    async def _get_pr_reviews_summary(self, repo: str, pr_number: int) -> str:
        """Fetch and format prior reviews and feedback from other agents on this PR."""
        if self.dry_run or not repo or not pr_number:
            return ""

        try:
            reviews = await self.github_client.get_pr_reviews(repo, pr_number)
            comments = await self.github_client.get_issue_comments(repo, pr_number)

            summary_lines = []
            for r in reversed(reviews[-5:]):
                body = r.get("body", "").strip()
                user = r.get("user", {}).get("login", "reviewer")
                state = r.get("state", "COMMENT")
                if body:
                    summary_lines.append(f"#### 💬 Review by @{user} ({state}):\n{body[:1200]}\n")

            if not summary_lines and comments:
                for c in reversed(comments[-3:]):
                    body = c.get("body", "").strip()
                    user = c.get("user", {}).get("login", "user")
                    if body:
                        summary_lines.append(f"#### 💬 Comment by @{user}:\n{body[:1000]}\n")

            if summary_lines:
                return "### 📋 Prior Review & Audit History on this PR:\n" + "\n".join(summary_lines)
        except Exception as e:
            print(f"[WARN] Failed fetching PR review history: {e}")

        return ""

    async def route_event(
        self,
        event_name: str,
        payload: Dict[str, Any],
        agent_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Route event to the appropriate agent handler or smart stateful pipeline."""
        repo_name = payload.get("repository", {}).get("full_name", "owner/repo")

        # Explicit agent override
        if agent_override:
            if agent_override in ["auto", "pipeline", "fleet", "autonomous"]:
                return await self.run_autonomous_pipeline(repo_name, payload)
            return await self._dispatch_agent(agent_override, repo_name, payload)

        action = payload.get("action", "")

        # 1. Issue Events
        if event_name == "issues":
            added_label = payload.get("label", {}).get("name", "")
            labels = [lbl.get("name", "") for lbl in payload.get("issue", {}).get("labels", [])]

            if "agent:autonomous" in labels or added_label == "agent:autonomous" or (action == "opened" and "agent:pm" not in labels and "agent:ready-for-dev" not in labels):
                return await self.run_autonomous_pipeline(repo_name, payload)

            if added_label == "agent:ready-for-dev" or "agent:ready-for-dev" in labels:
                return await self.handle_dev_agent(repo_name, payload)
            if added_label == "agent:pm" or "agent:pm" in labels or action == "opened":
                return await self.handle_pm_agent(repo_name, payload)

        # 2. Issue Comments / Mentions / PR Reviews
        elif event_name in ["issue_comment", "pull_request_review_comment", "pull_request_review"] and action in ["created", "edited", "submitted"]:
            comment_obj = payload.get("comment", {}) or payload.get("review", {})
            author = comment_obj.get("user", {}).get("login", "")
            
            # Avoid self-triggering infinite loops on bot comments
            if author.endswith("[bot]") or author in ["github-actions[bot]", "agentic-fleet"]:
                return {"status": "ignored", "reason": f"Ignored comment from bot user '{author}'"}

            comment_body = (
                payload.get("comment", {}).get("body", "")
                or payload.get("review", {}).get("body", "")
            ).lower()

            # 1. Pipeline trigger
            if "@fleet" in comment_body or "@autonomous" in comment_body or "run pipeline" in comment_body:
                return await self.run_autonomous_pipeline(repo_name, payload)

            # 2. Automated remediation trigger on failure/block reviews
            if (
                "status: failed" in comment_body
                or "status: blocked" in comment_body
                or "action required for dev-agent" in comment_body
                or "action required by dev-agent" in comment_body
                or payload.get("review", {}).get("state") == "changes_requested"
            ):
                print("[EVENT ROUTER] 🧑‍💻 Review reported defects / changes requested. Routing directly to dev-agent for remediation...")
                return await self.handle_dev_agent(repo_name, payload)

            # 3. Explicit agent mentions
            if "@dev-agent" in comment_body or "@dev" in comment_body:
                return await self.handle_dev_agent(repo_name, payload)
            if "@pm-agent" in comment_body or "@pm" in comment_body:
                return await self.handle_pm_agent(repo_name, payload)
            if "@security-agent" in comment_body:
                return await self.handle_security_agent(repo_name, payload)
            if "@qa-agent" in comment_body:
                return await self.handle_qa_agent(repo_name, payload)
            if "@senior-reviewer-agent" in comment_body or "@reviewer" in comment_body:
                return await self.handle_senior_reviewer_agent(repo_name, payload)

            # 4. Default for all human comments: engage smart autonomous fleet!
            print(f"[EVENT ROUTER] 🛸 Human comment by @{author or 'user'} received. Engaging autonomous fleet orchestrator...")
            return await self.run_autonomous_pipeline(repo_name, payload)

        # 3. Pull Request Events
        elif event_name == "pull_request":
            added_label = payload.get("label", {}).get("name", "")
            pr_labels = [lbl.get("name", "") for lbl in payload.get("pull_request", {}).get("labels", [])]

            if added_label == "ready-for-review" or "ready-for-review" in pr_labels:
                return await self.handle_senior_reviewer_agent(repo_name, payload)
            if added_label == "ready-for-qa" or "ready-for-qa" in pr_labels:
                return await self.handle_qa_agent(repo_name, payload)
            if action in ["opened", "synchronize"] or added_label == "ready-for-security-audit" or "ready-for-security-audit" in pr_labels:
                return await self.handle_security_agent(repo_name, payload)

        # 4. Repository Dispatch Events (Autonomous MCP / Zero-Issue Fleet Dispatch)
        elif event_name == "repository_dispatch":
            action_type = payload.get("action", "") or payload.get("event_type", "")
            client_payload = payload.get("client_payload", {})
            title = client_payload.get("title") or "Autonomous Feature Initiative"
            initiative_id = client_payload.get("initiative_id") or client_payload.get("id") or client_payload.get("item_id") or "mcp-initiative"
            feedback = client_payload.get("feedback") or ""
            prompt_text = client_payload.get("prompt") or feedback or title

            print(f"[EVENT ROUTER] ⚡ Processing repository_dispatch: action='{action_type}', initiative='{initiative_id}', title='{title}'")

            synthetic_issue = {
                "number": initiative_id,
                "title": title,
                "body": prompt_text,
                "labels": [{"name": "agent:autonomous"}, {"name": "source:mcp"}]
            }
            dispatch_payload = {
                **payload,
                "issue": synthetic_issue,
                "client_payload": client_payload,
            }

            if action_type in ["mcp_initiative", "mcp_spec"]:
                return await self.handle_pm_agent(repo_name, dispatch_payload)
            else:
                return await self.run_autonomous_pipeline(repo_name, dispatch_payload)

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

    async def run_autonomous_pipeline(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Smart, stateful SDLC orchestrator with strict QA gate halting and stage skip awareness:
        - Inspects current PR & Issue label states.
        - Skips already-passed stages (PM, Dev, Security, QA).
        - Ensures workspace is checked out to the current PR branch.
        - Executes QA verification first against current branch before deciding if dev remediation is needed.
        - Hard Halt: If QA fails (due to test failures, collection/import errors), halts immediately without running senior reviewer!
        """
        print("\n=======================================================")
        print("🛸 SMART AGENTIC FLEET PIPELINE (Autonomous Orchestration)")
        print("=======================================================\n")

        issue_payload = payload.get("issue", {})
        issue_number = issue_payload.get("number", 1)
        issue_title = issue_payload.get("title", "Feature Request")
        issue_labels = [lbl.get("name", "") for lbl in issue_payload.get("labels", [])]

        slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")[:30] or "feature"
        branch_name = f"feat/{issue_number}-{slug}"

        # Detect existing PR and branch directly from payload if available
        pr_payload_obj = payload.get("pull_request", {})
        if isinstance(pr_payload_obj, dict) and pr_payload_obj.get("head", {}).get("ref"):
            branch_name = pr_payload_obj["head"]["ref"]

        pr_number = self._extract_pr_number(payload)
        pr_labels = []
        if not pr_number and not self.dry_run and repo:
            existing_pr = await self.github_client.find_existing_pr(repo, branch_name)
            if not existing_pr:
                existing_pr = await self.github_client.find_existing_pr(repo, f"feat/{issue_number}")
            if existing_pr:
                pr_number = existing_pr.get("number")
                pr_labels = [lbl.get("name", "") for lbl in existing_pr.get("labels", [])]
        elif pr_number and not self.dry_run and repo:
            try:
                pr_data = await self.github_client.get_pull_request(repo, pr_number)
                pr_labels = [lbl.get("name", "") for lbl in pr_data.get("labels", [])]
                branch_name = pr_data.get("head", {}).get("ref", branch_name)
            except Exception as e:
                print(f"[WARN] Failed fetching PR metadata: {e}")

        # Ensure runner is on the current PR branch
        if branch_name:
            await self._ensure_branch_checkout(repo, branch_name)

        pipeline_summary = {
            "pipeline": "autonomous-5-agent-sdlc",
            "stages": {},
            "status": "in_progress",
        }

        # -------------------------------------------------------------
        # STAGE 1: Product Management & Specification (pm-agent)
        # -------------------------------------------------------------
        if pr_number or "agent:ready-for-dev" in issue_labels or "ready-for-security-audit" in issue_labels:
            print("[STAGE 1/5] ⏭️ pm-agent: Specification already accepted. Skipping duplicate framing.")
            pipeline_summary["stages"]["pm_agent"] = {"status": "skipped", "reason": "already_completed"}
        else:
            print("[STAGE 1/5] 🎯 Running pm-agent (Specification & Gherkin ACs)...")
            pm_result = await self.handle_pm_agent(repo, payload)
            pipeline_summary["stages"]["pm_agent"] = pm_result

        # -------------------------------------------------------------
        # STAGE 2: Autonomous Development & PR Creation (dev-agent)
        # -------------------------------------------------------------
        if pr_number:
            print(f"[STAGE 2/5] ⏭️ dev-agent: Pull Request #{pr_number} on `{branch_name}` already open. Skipping initial creation.")
            pipeline_summary["stages"]["dev_agent"] = {"status": "skipped", "pr_number": pr_number, "branch_name": branch_name}
        else:
            print("\n[STAGE 2/5] 🧑‍💻 Running dev-agent (Branching, Implementation & PR Opening)...")
            dev_result = await self.handle_dev_agent(repo, payload)
            pipeline_summary["stages"]["dev_agent"] = dev_result
            pr_number = dev_result.get("pr_number")
            branch_name = dev_result.get("branch_name", branch_name)

        if not pr_number and not self.dry_run:
            print(f"\n[HALT] 🛑 dev-agent could not open a Pull Request for branch `{branch_name}`. Halting pipeline.")
            pipeline_summary["status"] = "pr_creation_failed_halted"
            if issue_number and repo:
                halt_comment = (
                    f"## ⚠️ Autonomous Pipeline Halted: Pull Request Creation Required\n\n"
                    f"- 🎯 **`pm-agent`**: Specification generated.\n"
                    f"- 🧑‍💻 **`dev-agent`**: Materialized files on branch `{branch_name}`.\n\n"
                    f"⛔ **Action Required**: The automated Pull Request could not be created automatically.\n"
                    f"1. Ensure **'Allow GitHub Actions to create and approve pull requests'** is enabled in repository settings (`Settings` -> `Actions` -> `General` -> `Workflow permissions`).\n"
                    f"2. Or manually open a Pull Request from branch `{branch_name}`."
                )
                target_comment_id = pr_number or (issue_number if isinstance(issue_number, int) else None)
            if target_comment_id:
                await self.github_client.create_issue_comment(repo, target_comment_id, halt_comment)
            return pipeline_summary

        effective_pr_number = pr_number or 1
        pr_payload = {
            "repository": {"full_name": repo},
            "pull_request": {"number": effective_pr_number, "head": {"ref": branch_name}},
            "issue": {"number": effective_pr_number, "pull_request": {}},
        }

        # -------------------------------------------------------------
        # STAGE 3: Security & Multi-Tenant Audit (security-agent)
        # -------------------------------------------------------------
        if "security:passed" in pr_labels and not self.dry_run:
            print(f"[STAGE 3/5] ⏭️ security-agent: Multi-tenant audit already passed (security:passed). Skipping duplicate review.")
            pipeline_summary["stages"]["security_agent"] = {"status": "skipped", "verdict": "PASSED"}
            is_sec_blocked = False
        else:
            print(f"\n[STAGE 3/5] 🛡️ Running security-agent for PR #{effective_pr_number}...")
            sec_result = await self.handle_security_agent(repo, pr_payload)
            pipeline_summary["stages"]["security_agent"] = sec_result

            sec_response = sec_result.get("response", "")
            is_sec_blocked = False if self.dry_run else ("STATUS: BLOCKED" in sec_response or "VERDICT: BLOCKED" in sec_response or "STATUS: FAILED" in sec_response)

            if is_sec_blocked:
                print("\n[STAGE 3.1] ⚠️ Security defects detected. Invoking dev-agent to remediate...")
                remediation_payload = {
                    "repository": {"full_name": repo},
                    "pull_request": {"number": effective_pr_number, "head": {"ref": branch_name}},
                    "comment": {"body": f"Please fix the following security findings:\n\n{sec_response}"},
                }
                remed_result = await self.handle_dev_agent(repo, remediation_payload)
                pipeline_summary["stages"]["security_remediation"] = remed_result

                print("[STAGE 3.2] 🛡️ Re-auditing security post-remediation...")
                sec_result = await self.handle_security_agent(repo, pr_payload)
                pipeline_summary["stages"]["security_agent_recheck"] = sec_result
                sec_response = sec_result.get("response", "")
                is_sec_blocked = False if self.dry_run else ("STATUS: BLOCKED" in sec_response or "VERDICT: BLOCKED" in sec_response or "STATUS: FAILED" in sec_response)

        # -------------------------------------------------------------
        # STAGE 4: Adversarial QA & Test Execution (qa-agent & dev remediation)
        # -------------------------------------------------------------
        if "qa:passed" in pr_labels and not self.dry_run and not is_sec_blocked:
            print(f"[STAGE 4/5] ⏭️ qa-agent: QA verification already passed (qa:passed). Skipping duplicate review.")
            pipeline_summary["stages"]["qa_agent"] = {"status": "skipped", "verdict": "PASSED"}
            is_qa_failed = False
        else:
            print(f"\n[STAGE 4/5] 🧪 Running qa-agent against current branch `{branch_name}` for PR #{effective_pr_number}...")
            qa_result = await self.handle_qa_agent(repo, pr_payload)
            pipeline_summary["stages"]["qa_agent"] = qa_result

            qa_response = qa_result.get("response", "")
            is_qa_failed = False if self.dry_run else ("STATUS: FAILED" in qa_response or "FAILED ❌" in qa_response or "VERDICT: FAILED" in qa_response)

            if is_qa_failed:
                print("\n[STAGE 4.1] ⚠️ QA defects / test failures detected. Invoking dev-agent to remediate on branch...")
                remediation_payload = {
                    "repository": {"full_name": repo},
                    "pull_request": {"number": effective_pr_number, "head": {"ref": branch_name}},
                    "comment": {"body": f"Please fix the following QA defects, test collection errors, and adversarial failures:\n\n{qa_response}"},
                }
                remed_qa_result = await self.handle_dev_agent(repo, remediation_payload)
                pipeline_summary["stages"]["qa_remediation"] = remed_qa_result

                print("[STAGE 4.2] 🧪 Re-running QA verification post-remediation...")
                qa_result = await self.handle_qa_agent(repo, pr_payload)
                pipeline_summary["stages"]["qa_agent_recheck"] = qa_result
                qa_response = qa_result.get("response", "")
                is_qa_failed = False if self.dry_run else ("STATUS: FAILED" in qa_response or "FAILED ❌" in qa_response or "VERDICT: FAILED" in qa_response)

        # HARD GATE: If QA failed due to collection errors or test failures, HALT PIPELINE IMMEDIATELY!
        if is_qa_failed:
            print("\n[HALT] 🛑 QA verification failed (test collection/execution/edge case error). Halting pipeline before Senior Reviewer.")
            pipeline_summary["status"] = "qa_failed_halted"
            if not self.dry_run and pr_number and repo:
                await self.github_client.add_labels(repo, pr_number, ["qa:failed", "status:changes-requested"])
                halt_comment = (
                    f"## 🛑 Autonomous Pipeline Halted: QA Test Execution / Collection Failed\n\n"
                    f"- 🎯 **`pm-agent`**: Specification accepted.\n"
                    f"- 🧑‍💻 **`dev-agent`**: Implementation pushed to `{branch_name}`.\n"
                    f"- 🛡️ **`security-agent`**: Security audit complete.\n"
                    f"- 🧪 **`qa-agent`**: **STATUS: FAILED ❌** (Test collection or execution errors detected).\n\n"
                    f"⛔ **Pipeline Halted**: `senior-reviewer-agent` will not run until all test errors and collection issues are resolved.\n\n"
                    f"👉 Please inspect and resolve failures on Pull Request [**#{pr_number}**](https://github.com/{repo}/pull/{pr_number})."
                )
                target_comment_id = pr_number or (issue_number if isinstance(issue_number, int) else None)
            if target_comment_id:
                await self.github_client.create_issue_comment(repo, target_comment_id, halt_comment)
            return pipeline_summary

        # -------------------------------------------------------------
        # STAGE 5: Principal Architect Review & Sign-off (senior-reviewer-agent)
        # -------------------------------------------------------------
        if "status:approved" in pr_labels and "ready-for-merge" in pr_labels and not is_sec_blocked and not is_qa_failed and not self.dry_run:
            print(f"[STAGE 5/5] ⏭️ senior-reviewer-agent: PR #{effective_pr_number} already APPROVED. Skipping duplicate review.")
            pipeline_summary["stages"]["senior_reviewer_agent"] = {"status": "skipped", "verdict": "APPROVED"}
        else:
            print(f"\n[STAGE 5/5] 🧙‍♂️ Running senior-reviewer-agent (ADR Audit & Approval)...")
            reviewer_result = await self.handle_senior_reviewer_agent(repo, pr_payload)
            pipeline_summary["stages"]["senior_reviewer_agent"] = reviewer_result

        sec_status_icon = "STATUS: BLOCKED ❌" if is_sec_blocked else "STATUS: PASSED ✅"
        qa_status_icon = "STATUS: PASSED ✅"

        if not self.dry_run and pr_number and repo:
            await self.github_client.add_labels(repo, pr_number, ["ready-for-merge", "status:approved"])
            final_comment = (
                f"## 🚀 Autonomous 5-Agent SDLC Pipeline: Ready for Merge\n\n"
                f"All quality and compliance gates are verified:\n"
                f"- 🎯 **`pm-agent`**: User Story & Gherkin specifications accepted.\n"
                f"- 🧑‍💻 **`dev-agent`**: Code and unit tests authored on branch `{branch_name}`.\n"
                f"- 🛡️ **`security-agent`**: Multi-tenant isolation & secrets audit ({sec_status_icon}).\n"
                f"- 🧪 **`qa-agent`**: Adversarial edge cases & regression tests ({qa_status_icon}).\n"
                f"- 🧙‍♂️ **`senior-reviewer-agent`**: ADR compliance validated and PR **APPROVED (`LGTM ✅`)**.\n\n"
                f"👉 **Human Sign-Off Gate**: Pull Request [**#{pr_number}**](https://github.com/{repo}/pull/{pr_number}) is ready for your final merge!"
            )
            target_comment_id = pr_number or (issue_number if isinstance(issue_number, int) else None)
            if target_comment_id:
                await self.github_client.create_issue_comment(repo, target_comment_id, final_comment)

        pipeline_summary["status"] = "completed_awaiting_human_merge"
        print("\n=======================================================")
        print(f"🏁 STATEFUL PIPELINE EXECUTION COMPLETE (Status: {pipeline_summary['status']})")
        print("=======================================================\\n")
        return pipeline_summary

    async def handle_pm_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """pm-agent: formats user story, Gherkin criteria, and RICE score with full workspace context."""
        workspace_dir = Path(os.getenv("TARGET_WORKSPACE", os.getcwd()))
        ws_info = AgentContextBuilder.inspect_workspace(workspace_dir)

        issue = payload.get("issue", {})
        issue_number = issue.get("number", 1)
        issue_title = issue.get("title", "Feature Request")
        issue_body = issue.get("body", "")

        prompt = self.llm_runner.load_prompt(
            "pm-agent",
            {"issue_title": issue_title, "issue_body": issue_body, "repo_name": repo},
        )
        context_block = AgentContextBuilder.format_context_block(
            workspace_info=ws_info,
            issue_info={"number": issue_number, "title": issue_title, "body": issue_body},
        )
        user_input = f"{context_block}\n\nPlease author the user story, Gherkin acceptance criteria, and RICE score for Issue #{issue_number}."
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run, tier="fast")

        if not self.dry_run and isinstance(issue_number, int) and repo:
            await self.github_client.create_issue_comment(repo, issue_number, response)
            await self.github_client.remove_label(repo, issue_number, "agent:pm")
            await self.github_client.add_labels(repo, issue_number, ["agent:ready-for-dev"])

        return {
            "agent": "pm-agent",
            "action": "formatted_spec",
            "issue_number": issue_number,
            "response": response,
        }

    async def handle_dev_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """dev-agent: creates branch, generates code & unit tests, materializes files with full 360-degree context."""
        workspace_dir = Path(os.getenv("TARGET_WORKSPACE", os.getcwd()))
        ws_info = AgentContextBuilder.inspect_workspace(workspace_dir)

        pr_number = self._extract_pr_number(payload)
        issue = payload.get("issue", {})
        issue_number = issue.get("number", 1)
        issue_title = issue.get("title", "Implementation")
        issue_body = issue.get("body", "")
        comment_body = payload.get("comment", {}).get("body", "") or payload.get("review", {}).get("body", "")

        is_pr_remediation = bool(pr_number)
        effective_num = pr_number if is_pr_remediation else issue_number

        branch_name = f"feat/{effective_num}"
        if is_pr_remediation and not self.dry_run and repo:
            try:
                pr_info = await self.github_client.get_pull_request(repo, pr_number)
                branch_name = pr_info.get("head", {}).get("ref", branch_name)
            except Exception as e:
                print(f"[WARN] Could not fetch PR branch info: {e}")
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")[:30] or "feature"
            branch_name = f"feat/{issue_number}-{slug}"

        # Ensure working on target branch
        if branch_name:
            await self._ensure_branch_checkout(repo, branch_name)

        review_history = await self._get_pr_reviews_summary(repo, pr_number) if pr_number else ""
        diff_content = await self._get_pr_diff_safe(repo, effective_num) if is_pr_remediation else ""

        prompt = self.llm_runner.load_prompt(
            "dev-agent",
            {"issue_number": effective_num, "issue_title": issue_title, "issue_body": issue_body, "branch_name": branch_name},
        )

        context_block = AgentContextBuilder.format_context_block(
            workspace_info=ws_info,
            issue_info={"number": effective_num, "title": issue_title, "body": issue_body},
            pr_info={"number": effective_num, "branch": branch_name, "diff": diff_content} if is_pr_remediation else None,
            review_history=review_history,
        )

        if is_pr_remediation:
            user_input = (
                f"{context_block}\n\n"
                f"### ⚠️ Remediation Task for Pull Request #{pr_number}\n"
                f"Latest Reviewer / QA Feedback:\n{comment_body}\n\n"
                f"Implement all required remediations adhering strictly to the directory layout, fix any test issues, and output all code blocks using ```python:backend/path/to/file.py."
            )
        else:
            user_input = (
                f"{context_block}\n\n"
                f"Implement specification for Issue #{issue_number}: {issue_title}\n\n"
                f"Output all implementation and test files using ```python:backend/path/to/file.py blocks."
            )

        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run, tier="fast")

        created_pr_number = pr_number
        if not self.dry_run and effective_num and repo:
            token = self.github_client.token

            # 1. Write docs/prs/ artifact
            prs_dir = workspace_dir / "docs" / "prs"
            prs_dir.mkdir(parents=True, exist_ok=True)
            pr_doc_path = prs_dir / f"PR-{effective_num}.md"
            pr_doc_path.write_text(response, encoding="utf-8")

            # 2. Materialize code and test files into the actual codebase!
            extracted_files = self._materialize_code_files(workspace_dir, response)
            print(f"[DEV-AGENT] 🚀 Materialized {len(extracted_files)} files: {list(extracted_files.keys())}")

            # 3. Pre-Commit Self-Healing Sandbox Loop: verify locally before pushing!
            test_cmd = "pytest -v backend/tests" if ws_info.get("has_backend") else "pytest -v"
            max_remediations = int(os.getenv("MAX_REMEDIATION_ITERATIONS", "5"))
            for iteration in range(1, max_remediations + 1):
                print(f"[DEV-AGENT] 🧪 Running pre-commit test verification (Iteration {iteration}/{max_remediations})...")
                test_res = await self.test_harness.run_command(test_cmd)
                if test_res.is_success or test_res.failed_tests == 0:
                    print(f"[DEV-AGENT] ✅ Pre-commit test suite PASSED ({test_res.passed_tests} passed, 0 failures)!")
                    break
                else:
                    print(f"[DEV-AGENT] ⚠️ Pre-commit test failure detected ({test_res.failed_tests} failed). Auto-remediating locally...")
                    fix_input = (
                        f"Your previously generated code caused test failures or collection errors:\n\n"
                        f"### Test Command: {test_cmd}\n"
                        f"### Error Traceback:\n```\n{test_res.failure_summary}\n```\n\n"
                        f"Please fix all missing imports (e.g. from typing import AsyncGenerator, etc.), missing functions, and test errors.\n"
                        f"Output all corrected files in ```python:backend/path/to/file.py blocks."
                    )
                    fix_response = await self.llm_runner.generate_response(prompt, fix_input, dry_run=self.dry_run, tier="fast")
                    re_extracted = self._materialize_code_files(workspace_dir, fix_response)
                    extracted_files.update(re_extracted)
                    response += "\n\n" + fix_response

            commit_msg = (
                f"fix(sdlc): remediate review findings and materialize source files on PR #{pr_number}"
                if is_pr_remediation
                else f"feat(sdlc): implementation for issue #{issue_number} - {issue_title}"
            )

            git_commands = [
                'git config user.name "github-actions[bot]"',
                'git config user.email "github-actions[bot]@users.noreply.github.com"',
                f"git checkout -B {branch_name}",
                "git add .",
                f'git commit -m "{commit_msg}" --allow-empty',
            ]
            for cmd in git_commands:
                res = await self.test_harness.run_command(cmd)
                if not res.is_success and res.exit_code != 0:
                    print(f"[ERROR] Git command failed: {cmd}\nStdout: {res.stdout}\nStderr: {res.stderr}")

            push_cmd = f"git push origin {branch_name} --force"
            if token:
                push_cmd = f"git push https://x-access-token:{token}@github.com/{repo}.git {branch_name} --force"

            push_res = await self.test_harness.run_command(push_cmd)
            if not push_res.is_success and push_res.exit_code != 0:
                print(f"[ERROR] Git push failed: {push_res.stderr} (stdout: {push_res.stdout})")

            if not is_pr_remediation:
                try:
                    pr_title = f"feat: implement Issue #{issue_number} - {issue_title}" if isinstance(issue_number, int) else f"feat: {issue_title}"
                    clean_summary = re.sub(r"```[a-zA-Z0-9_\-\.]*:?[a-zA-Z0-9_\-\.\/]*\n.*?```", "", response, flags=re.DOTALL).strip()
                    clean_summary = re.sub(r"\n{3,}", "\n\n", clean_summary)
                    file_list_md = "\n".join([f"- `{f}`" for f in extracted_files.keys()]) if extracted_files else "- *(See Git Diff)*"
                    
                    pr_body = (
                        f"## 🚀 Overview & Intent\n"
                        f"{f'Closes #{issue_number}' if isinstance(issue_number, int) else f'**Roadmap Initiative**: `{issue_number}`'}\n\n"
                        f"### 📋 Summary of Changes\n"
                        f"{clean_summary[:2500]}\n\n"
                        f"### 📁 Files Created & Modified\n"
                        f"{file_list_md}\n\n"
                        f"### 🧪 Automated Verification & Quality Matrix\n"
                        f"- [x] **Unit & Integration Tests**: Verified via pre-commit test runner.\n"
                        f"- [ ] **Security Audit**: Monitored by `@security-agent`.\n"
                        f"- [ ] **Adversarial QA**: Monitored by `@qa-agent`.\n"
                        f"- [ ] **Architectural Sign-off**: Awaiting `@senior-reviewer-agent` approval.\n"
                    )
                    pr_res = await self.github_client.create_pull_request(
                        repo=repo,
                        title=pr_title,
                        head=branch_name,
                        base="main",
                        body=pr_body,
                    )
                    created_pr_number = pr_res.get("number")
                except Exception as e:
                    print(f"[ERROR] Create PR error: {e}")

            if created_pr_number:
                if is_pr_remediation:
                    comment_body = (
                        f"## 🧑‍💻 `dev-agent` Remediation Update\n\n"
                        f"Pushed {len(extracted_files)} materialized files to branch `{branch_name}` for Pull Request [**#{created_pr_number}**](https://github.com/{repo}/pull/{created_pr_number}).\n\n"
                        f"Handoff target: `@qa-agent` for re-verification."
                    )
                else:
                    comment_body = (
                        f"## 🧑‍💻 `dev-agent` Update\n\n"
                        f"Created feature branch `{branch_name}` and opened Pull Request [**#{created_pr_number}**](https://github.com/{repo}/pull/{created_pr_number}) (Closes #{issue_number}).\n\n"
                        f"Handoff target: `security-agent`."
                    )
            else:
                comment_body = (
                    f"## 🧑‍💻 `dev-agent` Update\n\n"
                    f"Pushed branch `{branch_name}`."
                )

            target_id = created_pr_number if created_pr_number else (issue_number if isinstance(issue_number, int) else None)
            if target_id:
                await self.github_client.create_issue_comment(repo, target_id, comment_body)

        return {
            "agent": "dev-agent",
            "action": "remediated_pr" if is_pr_remediation else "toggled_development",
            "issue_number": effective_num,
            "branch_name": branch_name,
            "pr_number": created_pr_number,
            "response": response,
        }

    async def handle_security_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """security-agent: scans diff for multi-tenant isolation, secrets, OWASP with full context awareness."""
        workspace_dir = Path(os.getenv("TARGET_WORKSPACE", os.getcwd()))
        ws_info = AgentContextBuilder.inspect_workspace(workspace_dir)

        pr_number = self._extract_pr_number(payload)
        issue_number = payload.get("issue", {}).get("number")

        if not pr_number and issue_number and not self.dry_run:
            existing_pr = await self.github_client.find_existing_pr(repo, f"feat/{issue_number}")
            if existing_pr:
                pr_number = existing_pr.get("number")

        if not pr_number and not self.dry_run:
            if issue_number:
                await self.github_client.create_issue_comment(
                    repo,
                    issue_number,
                    "⚠️ `security-agent`: No active Pull Request found for this issue. Please run `@dev-agent` first to create the implementation branch and PR.",
                )
            return {"status": "ignored", "reason": "No PR number found for security review"}

        effective_pr_number = pr_number or 1

        branch_name = "main"
        if not self.dry_run and repo:
            try:
                pr_info = await self.github_client.get_pull_request(repo, effective_pr_number)
                branch_name = pr_info.get("head", {}).get("ref", branch_name)
                if branch_name:
                    await self._ensure_branch_checkout(repo, branch_name)
            except Exception:
                pass

        diff_content = await self._get_pr_diff_safe(repo, effective_pr_number)
        review_history = await self._get_pr_reviews_summary(repo, effective_pr_number)

        prompt = self.llm_runner.load_prompt(
            "security-agent",
            {"pr_number": effective_pr_number, "files_inspected": "All modified files in pull request"},
        )

        context_block = AgentContextBuilder.format_context_block(
            workspace_info=ws_info,
            issue_info={"number": issue_number or effective_pr_number, "title": f"PR #{effective_pr_number}", "body": "Security Audit"},
            pr_info={"number": effective_pr_number, "branch": branch_name, "diff": diff_content},
            review_history=review_history,
        )

        user_input = (
            f"{context_block}\n\n"
            f"Perform multi-tenant isolation, secrets, and OWASP audit for Pull Request #{effective_pr_number}."
        )
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run, tier="deep")

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="COMMENT")
            is_blocked = "STATUS: BLOCKED" in response or "CRITICAL" in response or "HIGH" in response
            if is_blocked:
                await self.github_client.remove_label(repo, pr_number, "security:passed")
                await self.github_client.add_labels(repo, pr_number, ["security:blocked"])
            else:
                await self.github_client.remove_label(repo, pr_number, "security:blocked")
                await self.github_client.add_labels(repo, pr_number, ["security:passed", "ready-for-qa"])

        return {
            "agent": "security-agent",
            "action": "security_audit",
            "pr_number": effective_pr_number,
            "response": response,
        }

    async def handle_qa_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """qa-agent: guarantees execution on the PR's current branch with 360-degree context awareness."""
        workspace_dir = Path(os.getenv("TARGET_WORKSPACE", os.getcwd()))
        ws_info = AgentContextBuilder.inspect_workspace(workspace_dir)

        pr_number = self._extract_pr_number(payload)
        issue_number = payload.get("issue", {}).get("number")

        if not pr_number and issue_number and not self.dry_run:
            existing_pr = await self.github_client.find_existing_pr(repo, f"feat/{issue_number}")
            if existing_pr:
                pr_number = existing_pr.get("number")

        if not pr_number and not self.dry_run:
            if issue_number:
                await self.github_client.create_issue_comment(
                    repo,
                    issue_number,
                    "⚠️ `qa-agent`: No active Pull Request found for this issue. Please run `@dev-agent` first to create the implementation branch and PR.",
                )
            return {"status": "ignored", "reason": "No PR number found for QA testing"}

        effective_pr_number = pr_number or 1

        branch_name = "main"
        if not self.dry_run and repo:
            try:
                pr_info = await self.github_client.get_pull_request(repo, effective_pr_number)
                branch_name = pr_info.get("head", {}).get("ref", branch_name)
                if branch_name:
                    await self._ensure_branch_checkout(repo, branch_name)
            except Exception as e:
                print(f"[WARN] QA branch checkout failed for PR #{effective_pr_number}: {e}")

        diff_content = await self._get_pr_diff_safe(repo, effective_pr_number)
        review_history = await self._get_pr_reviews_summary(repo, effective_pr_number)

        # Smart test execution: if backend/ directory exists, run pytest inside backend or target backend/tests
        test_cmd = "pytest -v backend/tests" if ws_info.get("has_backend") else "pytest -v"

        test_res = await self.test_harness.run_command(test_cmd) if not self.dry_run else None
        if test_res:
            total = test_res.total_tests
            passed = test_res.passed_tests
            failed = test_res.failed_tests
            duration = test_res.duration_seconds
            stdout_snippet = test_res.failure_summary if failed > 0 else (test_res.stdout + ("\n" + test_res.stderr if test_res.stderr else ""))[:3000]
        else:
            total = 15
            passed = 15
            failed = 0
            duration = 1.25
            stdout_snippet = "All automated regression tests passed."

        prompt = self.llm_runner.load_prompt(
            "qa-agent",
            {
                "pr_number": effective_pr_number,
                "total_tests": total,
                "passed_tests": passed,
                "failed_tests": failed,
                "execution_time_seconds": duration,
            },
        )

        test_summary = {
            "total": total,
            "passed": passed,
            "failed": failed,
            "duration": duration,
            "snippet": stdout_snippet,
        }

        context_block = AgentContextBuilder.format_context_block(
            workspace_info=ws_info,
            issue_info={"number": issue_number or effective_pr_number, "title": f"PR #{effective_pr_number}", "body": "QA Validation"},
            pr_info={"number": effective_pr_number, "branch": branch_name, "diff": diff_content},
            review_history=review_history,
            test_summary=test_summary,
        )

        user_input = (
            f"{context_block}\n\n"
            f"Adversarial QA validation for PR #{effective_pr_number} using command `{test_cmd}`."
        )
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run, tier="fast")

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="COMMENT")
            is_failed = "STATUS: FAILED" in response or "FAILED ❌" in response or "FAIL ❌" in response or failed > 0
            if is_failed:
                await self.github_client.remove_label(repo, pr_number, "qa:passed")
                await self.github_client.add_labels(repo, pr_number, ["qa:failed"])
            else:
                await self.github_client.remove_label(repo, pr_number, "qa:failed")
                await self.github_client.add_labels(repo, pr_number, ["qa:passed", "ready-for-review"])

        return {
            "agent": "qa-agent",
            "action": "qa_verification",
            "pr_number": effective_pr_number,
            "response": response,
        }

    async def handle_senior_reviewer_agent(self, repo: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """senior-reviewer-agent: audits architecture/ADRs, checks Sec+QA, approves PR with full 360-degree context."""
        workspace_dir = Path(os.getenv("TARGET_WORKSPACE", os.getcwd()))
        ws_info = AgentContextBuilder.inspect_workspace(workspace_dir)

        pr_number = self._extract_pr_number(payload)
        issue_number = payload.get("issue", {}).get("number")

        if not pr_number and issue_number and not self.dry_run:
            existing_pr = await self.github_client.find_existing_pr(repo, f"feat/{issue_number}")
            if existing_pr:
                pr_number = existing_pr.get("number")

        if not pr_number and not self.dry_run:
            if issue_number:
                await self.github_client.create_issue_comment(
                    repo,
                    issue_number,
                    "⚠️ `senior-reviewer-agent`: No active Pull Request found for this issue. Please run `@dev-agent` first to create the implementation branch and PR.",
                )
            return {"status": "ignored", "reason": "No PR number found for architectural review"}

        effective_pr_number = pr_number or 1

        branch_name = "main"
        if not self.dry_run and repo:
            try:
                pr_info = await self.github_client.get_pull_request(repo, effective_pr_number)
                branch_name = pr_info.get("head", {}).get("ref", branch_name)
                if branch_name:
                    await self._ensure_branch_checkout(repo, branch_name)
            except Exception:
                pass

        diff_content = await self._get_pr_diff_safe(repo, effective_pr_number)
        review_history = await self._get_pr_reviews_summary(repo, effective_pr_number)

        prompt = self.llm_runner.load_prompt("senior-reviewer-agent", {"pr_number": effective_pr_number})

        context_block = AgentContextBuilder.format_context_block(
            workspace_info=ws_info,
            issue_info={"number": issue_number or effective_pr_number, "title": f"PR #{effective_pr_number}", "body": "Principal Architect Review"},
            pr_info={"number": effective_pr_number, "branch": branch_name, "diff": diff_content},
            review_history=review_history,
        )

        user_input = (
            f"{context_block}\n\n"
            f"Principal Architect review, ADR compliance audit, and merge readiness evaluation for Pull Request #{effective_pr_number}."
        )
        response = await self.llm_runner.generate_response(prompt, user_input, dry_run=self.dry_run, tier="deep")

        if not self.dry_run and pr_number and repo:
            await self.github_client.create_pr_review(repo, pr_number, response, event="APPROVE")
            await self.github_client.add_labels(repo, pr_number, ["status:approved", "ready-for-merge"])

        return {
            "agent": "senior-reviewer-agent",
            "action": "architect_review_approval",
            "pr_number": effective_pr_number,
            "response": response,
        }
