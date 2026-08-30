"""
GitHub REST API client for agentic-fleet orchestration.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
import httpx


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
            self.headers["Authorization"] = f"token {self.token}"

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
            resp.raise_for_status()
            return resp.json()

    async def add_labels(self, repo: str, issue_number: int, labels: List[str]) -> List[Dict[str, Any]]:
        """Add one or more labels to an issue or pull request."""
        async with self._get_client() as client:
            resp = await client.post(
                f"/repos/{repo}/issues/{issue_number}/labels",
                json={"labels": labels},
            )
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

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
        draft: bool = False,
    ) -> Dict[str, Any]:
        """Create a new pull request."""
        async with self._get_client() as client:
            resp = await client.post(
                f"/repos/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body, "draft": draft},
            )
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
