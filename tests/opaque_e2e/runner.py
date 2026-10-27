"""Standalone Opaque-Box E2E Test Suite Runner for OffGridUSB.

Runs Tiers 1-4 requirement-driven tests with zero external dependencies.
Supports per-tier execution, target drive configuration, and JSON export.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

if sys.platform == "win32":
    _orig_td_init = tempfile.TemporaryDirectory.__init__

    def _patched_td_init(self, *args, **kwargs):
        kwargs.setdefault("ignore_cleanup_errors", True)
        _orig_td_init(self, *args, **kwargs)

    tempfile.TemporaryDirectory.__init__ = _patched_td_init


def run_e2e_tests(
    tier: str = "all",
    target: str = "D:",
    json_path: str = "",
    verbosity: int = 2,
) -> int:
    """Executes the OffGridUSB opaque-box E2E test suite.

    Args:
        tier: '1', '2', '3', '4', or 'all'.
        target: Target drive path (e.g. 'D:').
        json_path: Optional path to save structured JSON test results.
        verbosity: unittest verbosity level (1 or 2).

    Returns:
        0 on success, non-zero if tests failed or errored.
    """
    if target:
        os.environ["OFFGRID_TARGET_DRIVE"] = target

    suite_dir = Path(__file__).resolve().parent
    repo_root = suite_dir.parent.parent

    # Ensure src is on sys.path
    src_dir = repo_root / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    tier_map = {
        "1": ["test_tier1_features.py"],
        "2": ["test_tier2_boundaries.py"],
        "3": ["test_tier3_combinations.py"],
        "4": ["test_tier4_scenarios.py"],
        "all": [
            "test_tier1_features.py",
            "test_tier2_boundaries.py",
            "test_tier3_combinations.py",
            "test_tier4_scenarios.py",
        ],
    }

    test_files = tier_map.get(tier.lower(), tier_map["all"])

    print("=" * 72)
    print("  OffGridUSB Opaque-Box E2E Test Runner")
    print(f"  Target Drive / Path: {target}")
    print(f"  Execution Tier:      {tier.upper()}")
    print(f"  Test Files:          {', '.join(test_files)}")
    print("=" * 72)

    for tf in test_files:
        module_path = suite_dir / tf
        if module_path.exists():
            mod_name = f"tests.opaque_e2e.{tf[:-3]}"
            sub_suite = loader.discover(start_dir=str(suite_dir), pattern=tf)
            suite.addTests(sub_suite)

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)
    elapsed = round(time.time() - start_time, 3)

    passed_count = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)

    print("\n" + "=" * 72)
    print("  TEST EXECUTION SUMMARY")
    print("-" * 72)
    print(f"  Total Tests Executed: {result.testsRun}")
    print(f"  Passed:               {passed_count}")
    print(f"  Failures:             {len(result.failures)}")
    print(f"  Errors:               {len(result.errors)}")
    print(f"  Skipped:              {len(result.skipped)}")
    print(f"  Elapsed Time:         {elapsed}s")
    print("=" * 72)

    if json_path:
        summary_data = {
            "tier": tier,
            "target": target,
            "total": result.testsRun,
            "passed": passed_count,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "elapsed_seconds": elapsed,
            "was_successful": result.wasSuccessful(),
            "failure_details": [
                {"test": str(test), "trace": trace} for test, trace in result.failures
            ],
            "error_details": [
                {"test": str(test), "trace": trace} for test, trace in result.errors
            ],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        print(f"  Structured results written to: {json_path}")

    return 0 if result.wasSuccessful() else 1


def main():
    parser = argparse.ArgumentParser(description="Run OffGridUSB Opaque-Box E2E Tests.")
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Test tier to execute (default: all)",
    )
    parser.add_argument(
        "--target",
        default="D:",
        help="Target drive letter or deployment path (default: D:)",
    )
    parser.add_argument(
        "--json",
        default="",
        help="Optional path to output structured JSON test summary",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose test reporting",
    )
    args = parser.parse_args()

    exit_code = run_e2e_tests(
        tier=args.tier,
        target=args.target,
        json_path=args.json,
        verbosity=2 if args.verbose else 1,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
