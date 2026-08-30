"""
Test harness for running and evaluating automated test suites.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class TestResult:
    """Structured test suite execution outcome."""
    command: str
    exit_code: int
    duration_seconds: float
    stdout: str
    stderr: str
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and self.failed_tests == 0


class TestHarness:
    """Runner harness for automated test and linter execution."""
    __test__ = False  # Prevent pytest from attempting to collect this as a test class

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    async def run_command(self, command: str, timeout: float = 300.0) -> TestResult:
        """Execute a test or lint command and parse standard metrics."""
        start_time = time.time()
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=self.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            duration = time.time() - start_time
            return TestResult(
                command=command,
                exit_code=-1,
                duration_seconds=round(duration, 2),
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=f"Execution timed out after {timeout} seconds",
            )

        duration = round(time.time() - start_time, 2)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        total, passed, failed, skipped = self._parse_pytest_counts(stdout + "\n" + stderr)

        return TestResult(
            command=command,
            exit_code=process.returncode or 0,
            duration_seconds=duration,
            stdout=stdout,
            stderr=stderr,
            total_tests=total,
            passed_tests=passed,
            failed_tests=failed,
            skipped_tests=skipped,
        )

    def _parse_pytest_counts(self, output: str) -> tuple[int, int, int, int]:
        """Extract test counts from pytest or vitest output."""
        passed = 0
        failed = 0
        skipped = 0

        passed_match = re.search(r"(\d+)\s+passed", output, re.IGNORECASE)
        if passed_match:
            passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", output, re.IGNORECASE)
        if failed_match:
            failed = int(failed_match.group(1))

        skipped_match = re.search(r"(\d+)\s+skipped", output, re.IGNORECASE)
        if skipped_match:
            skipped = int(skipped_match.group(1))

        total = passed + failed + skipped
        return total, passed, failed, skipped
