"""
Test runner — discovers and runs all test_*.py files.

Prints ✓ or ✗ for each test, a final score, and exits
with code 1 if any tests failed. Used by GitHub Actions
to gate the pipeline — tests must pass before main.py runs.

Usage:
    python tests/run_tests.py
"""

import os
import sys
import unittest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class CompactTestResult(unittest.TextTestResult):
    """
    Custom test result that prints a single line per test
    with ✓ for pass, ✗ for fail, and S for skip.
    """

    def addSuccess(self, test):
        super().addSuccess(test)
        self.stream.write(f"  ✓ {test}\n")
        self.stream.flush()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.stream.write(f"  ✗ {test}\n")
        self.stream.flush()

    def addError(self, test, err):
        super().addError(test, err)
        self.stream.write(f"  ✗ {test} (error)\n")
        self.stream.flush()

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.stream.write(f"  S {test} — {reason}\n")
        self.stream.flush()


class CompactTestRunner(unittest.TextTestRunner):
    """Test runner that uses our compact result format."""
    resultclass = CompactTestResult

    def run(self, test):
        self.stream.write("\n")
        return super().run(test)


def main():
    print("=" * 50)
    print("RUNNING TESTS")
    print("=" * 50)

    # Discover all test_*.py files in the tests/ directory
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, pattern="test_*.py")

    # Count total tests (including those that will be skipped)
    total = suite.countTestCases()
    print(f"\nFound {total} tests\n")

    # Run with our compact output format
    runner = CompactTestRunner(verbosity=0)
    result = runner.run(suite)

    # Summary
    passed = result.testsRun - len(result.failures) - len(result.errors)
    skipped = len(result.skipped)
    failed = len(result.failures) + len(result.errors)

    print("\n" + "=" * 50)
    print(f"  {passed}/{result.testsRun} tests passed", end="")
    if skipped:
        print(f" ({skipped} skipped)", end="")
    if failed:
        print(f" ({failed} FAILED)", end="")
    print()
    print("=" * 50)

    # Exit with failure code if any tests failed
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
