import pytest
from src.test_harness import TestHarness


@pytest.mark.asyncio
async def test_run_command_success():
    harness = TestHarness()
    res = await harness.run_command("echo '=== 5 passed, 0 failed in 0.5s ==='")
    assert res.exit_code == 0
    assert res.passed_tests == 5
    assert res.failed_tests == 0
    assert res.is_success is True


@pytest.mark.asyncio
async def test_run_command_failure():
    harness = TestHarness()
    res = await harness.run_command("echo '=== 3 passed, 2 failed in 0.8s ===' && exit 1")
    assert res.exit_code == 1
    assert res.passed_tests == 3
    assert res.failed_tests == 2
    assert res.is_success is False


def test_parse_pytest_counts():
    harness = TestHarness()
    out = "====== 10 passed, 2 failed, 1 skipped in 1.45s ======"
    total, passed, failed, skipped = harness._parse_pytest_counts(out)
    assert total == 13
    assert passed == 10
    assert failed == 2
    assert skipped == 1
