"""
GitHub REST API client for agentic-fleet orchestration.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("agentic-fleet.github_client")


class GitHubClient:
    """Async GitHub REST API Client using httpx."""

    def __init__(self, token: Optional[str] = None, base_url: str = "https://api.github.com"):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "agentic-fleet-orchestrator",
        }
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=30.0)

    async def get_issue(self, repo: str, issue_number: int) -> Dict[str, Any]:
        """Fetch issue details by number."""
        async with self._get_client() as client:
            resp = await client.get(f"/repos/{repo}/issues/{issue_number}")
            resp.raise_for_status()
            return resp.json()

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

            # Try prefixing head with owner (e.g. dipeshsingh2012:feat/...)
            if ":" not in head and "/" in repo:
                owner = repo.split("/")[0]
                namespaced_head = f"{owner}:{head}"
                payload["head"] = namespaced_head
                print(f"[INFO] Retrying with namespaced head: '{namespaced_head}'")
                retry_resp = await client.post(f"/repos/{repo}/pulls", json=payload)
                if retry_resp.status_code in [200, 201]:
                    return retry_resp.json()
                print(f"[WARN] Namespaced PR retry failed: HTTP {retry_resp.status_code}: {retry_resp.text}")

            # Check if PR already exists for this branch
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
        """Submit a formal PR review (COMMENT, APPROVE, REQUEST_CHANGES)."""
        async with self._get_client() as client:
            resp = await client.post(
                f"/repos/{repo}/pulls/{pr_number}/reviews",
                json={"body": body, "event": event},
            )
            resp.raise_for_status()
            return resp.json()

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
