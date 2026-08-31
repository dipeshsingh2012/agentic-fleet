"""
Asynchronous GitHub REST API client using httpx.
Supports Issues, Pull Requests, Reviews, Inline Diff Comments, Labels, and Review History.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("agentic-fleet.github_client")


class GitHubClient:
    """Async GitHub REST API Client using httpx."""

    def __init__(
        self,
        token: Optional[str] = None,
        reviewer_token: Optional[str] = None,
        base_url: str = "https://api.github.com",
    ):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.reviewer_token = reviewer_token or os.getenv("REVIEWER_GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "agentic-fleet-orchestrator",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _get_client(self, use_reviewer_token: bool = False) -> httpx.AsyncClient:
        headers = dict(self.headers)
        if use_reviewer_token and self.reviewer_token:
            headers["Authorization"] = f"Bearer {self.reviewer_token}"
        return httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0)

    async def get_issue(self, repo: str, issue_number: int) -> Dict[str, Any]:
        """Fetch issue details by number."""
        async with self._get_client() as client:
            resp = await client.get(f"/repos/{repo}/issues/{issue_number}")
            resp.raise_for_status()
            return resp.json()

    async def get_issue_comments(self, repo: str, issue_number: int) -> List[Dict[str, Any]]:
        """Fetch all comments on an issue or PR."""
        async with self._get_client() as client:
            resp = await client.get(f"/repos/{repo}/issues/{issue_number}/comments", params={"per_page": 30})
            if resp.status_code == 200:
                return resp.json()
            return []

    async def get_pr_reviews(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        """Fetch all submitted reviews on a pull request."""
        async with self._get_client() as client:
            resp = await client.get(f"/repos/{repo}/pulls/{pr_number}/reviews", params={"per_page": 30})
            if resp.status_code == 200:
                return resp.json()
            return []

    async def create_issue_comment(self, repo: str, issue_number: int, body: str) -> Dict[str, Any]:
        """Post a comment on an issue or pull request."""
        async with self._get_client() as client:
            resp = await client.post(
                f"/repos/{repo}/issues/{issue_number}/comments",
                json={"body": body},
            )
            if resp.status_code not in [200, 201]:
                print(f"[ERROR] create_issue_comment failed: HTTP {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()

    async def add_labels(self, repo: str, issue_number: int, labels: List[str]) -> List[Dict[str, Any]]:
        """Add one or more labels to an issue or pull request."""
        async with self._get_client() as client:
            resp = await client.post(
                f"/repos/{repo}/issues/{issue_number}/labels",
                json={"labels": labels},
            )
            if resp.status_code not in [200, 201]:
                print(f"[ERROR] add_labels failed: HTTP {resp.status_code}: {resp.text}")
            resp.raise_for_status()
            return resp.json()

    async def remove_label(self, repo: str, issue_number: int, label: str) -> Optional[Dict[str, Any]]:
        """Remove a specific label from an issue or pull request."""
        async with self._get_client() as client:
            resp = await client.delete(f"/repos/{repo}/issues/{issue_number}/labels/{label}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    async def get_pull_request(self, repo: str, pr_number: int) -> Dict[str, Any]:
        """Fetch pull request metadata."""
        async with self._get_client() as client:
            resp = await client.get(f"/repos/{repo}/pulls/{pr_number}")
            resp.raise_for_status()
            return resp.json()

    async def get_pr_diff(self, repo: str, pr_number: int) -> str:
        """Fetch pull request diff content."""
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.diff"
        async with httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=30.0) as client:
            resp = await client.get(f"/repos/{repo}/pulls/{pr_number}")
            resp.raise_for_status()
            return resp.text

    async def find_existing_pr(self, repo: str, head_branch: str) -> Optional[Dict[str, Any]]:
        """Find an existing open PR by head branch."""
        async with self._get_client() as client:
            owner = repo.split("/")[0] if "/" in repo else ""
            query_heads = [head_branch, f"{owner}:{head_branch}"] if owner else [head_branch]
            for h in query_heads:
                resp = await client.get(f"/repos/{repo}/pulls", params={"head": h, "state": "open"})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data[0]
            return None

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> Dict[str, Any]:
        """Create a new pull request with automatic owner prefixing and existing PR detection."""
        async with self._get_client() as client:
            payload = {"title": title, "head": head, "base": base, "body": body, "draft": draft}
            print(f"[INFO] Calling GitHub API POST /repos/{repo}/pulls (head: '{head}', base: '{base}')")
            resp = await client.post(f"/repos/{repo}/pulls", json=payload)

            if resp.status_code in [200, 201]:
                return resp.json()

            print(f"[WARN] First PR creation attempt failed: HTTP {resp.status_code}: {resp.text}")

            if ":" not in head and "/" in repo:
                owner = repo.split("/")[0]
                namespaced_head = f"{owner}:{head}"
                payload["head"] = namespaced_head
                print(f"[INFO] Retrying with namespaced head: '{namespaced_head}'")
                retry_resp = await client.post(f"/repos/{repo}/pulls", json=payload)
                if retry_resp.status_code in [200, 201]:
                    return retry_resp.json()
                print(f"[WARN] Namespaced PR retry failed: HTTP {retry_resp.status_code}: {retry_resp.text}")

            existing_pr = await self.find_existing_pr(repo, head)
            if existing_pr:
                print(f"[INFO] Found existing open PR #{existing_pr.get('number')} for branch '{head}'")
                return existing_pr

            resp.raise_for_status()
            return resp.json()

    async def create_pr_review(
        self,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",
    ) -> Dict[str, Any]:
        """Submit a PR review (supports separate REVIEWER_GITHUB_TOKEN to avoid self-review 422)."""
        # If event is APPROVE, try using reviewer token if available
        use_rev_token = bool(self.reviewer_token and event == "APPROVE")
        async with self._get_client(use_reviewer_token=use_rev_token) as client:
            payload = {"body": body, "event": event}
            resp = await client.post(
                f"/repos/{repo}/pulls/{pr_number}/reviews",
                json=payload,
            )

            # If APPROVE failed with 422 (e.g. self-review restriction on single token)
            if resp.status_code == 422 and event != "COMMENT":
                print(f"[WARN] PR review with event '{event}' returned 422 (self-review restriction). Retrying with event='COMMENT'...")
                payload["event"] = "COMMENT"
                retry_resp = await client.post(
                    f"/repos/{repo}/pulls/{pr_number}/reviews",
                    json=payload,
                )
                if retry_resp.status_code in [200, 201]:
                    return retry_resp.json()

                print(f"[INFO] Fallback to standard PR issue comment...")
                return await self.create_issue_comment(repo, pr_number, body)

            resp.raise_for_status()
            return resp.json()

    async def create_inline_pr_comment(
        self,
        repo: str,
        pr_number: int,
        commit_id: str,
        path: str,
        line: int,
        body: str,
    ) -> Dict[str, Any]:
        """Post an inline review comment/suggestion directly on a specific line of code diff in a PR."""
        async with self._get_client() as client:
            payload = {
                "body": body,
                "commit_id": commit_id,
                "path": path,
                "line": line,
                "side": "RIGHT",
            }
            resp = await client.post(f"/repos/{repo}/pulls/{pr_number}/comments", json=payload)
            if resp.status_code in [200, 201]:
                return resp.json()
            print(f"[WARN] Inline comment failed HTTP {resp.status_code}: {resp.text}")
            return {}

    async def merge_pull_request(
        self,
        repo: str,
        pr_number: int,
        merge_method: str = "squash",
        commit_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Squash and merge a pull request."""
        payload: Dict[str, Any] = {"merge_method": merge_method}
        if commit_title:
            payload["commit_title"] = commit_title
        async with self._get_client() as client:
            resp = await client.put(
                f"/repos/{repo}/pulls/{pr_number}/merge",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()
