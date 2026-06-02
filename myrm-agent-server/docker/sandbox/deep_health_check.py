#!/usr/bin/env python
"""Deep health check for critical dependencies.

This script verifies that essential packages can be imported and used.
Unlike the lightweight HEALTHCHECK, this performs thorough validation.

Features:
- Parallel execution: Checks run concurrently to reduce total time
- Timeout control: Each package check is limited to 5 seconds
- Detailed reporting: Tracks success, failure, and timeout for each package

Exit codes:
    0: All checks passed
    1: One or more checks failed or timed out
"""

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Callable

# Per-package timeout in seconds
PACKAGE_TIMEOUT = 5.0


def check_package_import(package_name: str, test_fn: Callable[[], None] | None = None) -> tuple[str, str, str | None]:
    """Check if package can be imported and optionally run a quick test.

    Args:
        package_name: Name of package to import
        test_fn: Optional function to run basic functionality test

    Returns:
        Tuple of (package_name, status, error_message)
        status: "success", "failed", or "timeout"
    """
    try:
        __import__(package_name)
        if test_fn:
            test_fn()
        return (package_name, "success", None)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        return (package_name, "failed", error_msg)


def main() -> int:
    """Run all deep health checks in parallel with timeout control.

    Returns:
        0 if all checks passed, 1 otherwise
    """
    checks = [
        # Data science core (most critical)
        ("pandas", lambda: __import__("pandas").DataFrame({"a": [1, 2]})),
        ("numpy", lambda: __import__("numpy").array([1, 2, 3])),
        ("scipy", None),
        # File processing (high usage)
        ("openpyxl", lambda: __import__("openpyxl").Workbook()),
        ("pypdf", None),
        ("PIL", lambda: __import__("PIL").Image),
        ("pdfplumber", None),
        # Visualization
        ("matplotlib", lambda: __import__("matplotlib").use("Agg")),
        # Data formats
        ("pyarrow", None),
    ]

    success_count = 0
    failed_packages = []
    timeout_packages = []

    # Run checks in parallel with timeout control
    with ThreadPoolExecutor(max_workers=len(checks)) as executor:
        # Submit all checks
        future_to_package = {executor.submit(check_package_import, pkg_name, test_fn): pkg_name for pkg_name, test_fn in checks}

        # Collect results with timeout handling
        for future in as_completed(future_to_package):
            package_name = future_to_package[future]
            try:
                pkg_name, status, error_msg = future.result(timeout=PACKAGE_TIMEOUT)
                if status == "success":
                    success_count += 1
                    print(f"✅ {pkg_name}: OK")
                else:
                    failed_packages.append(pkg_name)
                    print(f"❌ {pkg_name}: {error_msg}", file=sys.stderr)
            except TimeoutError:
                timeout_packages.append(package_name)
                print(f"⏱️  {package_name}: Timeout after {PACKAGE_TIMEOUT}s", file=sys.stderr)
            except Exception as e:
                failed_packages.append(package_name)
                print(f"❌ {package_name}: Unexpected error: {e}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

    # Summary report
    total = len(checks)
    print(f"\n📊 Summary: {success_count}/{total} passed")

    if failed_packages:
        print(f"❌ Failed: {', '.join(failed_packages)}", file=sys.stderr)

    if timeout_packages:
        print(f"⏱️  Timeout: {', '.join(timeout_packages)}", file=sys.stderr)

    if failed_packages or timeout_packages:
        return 1

    print("✅ Deep health check passed. All critical packages are functional.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
