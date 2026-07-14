from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "demo/adversarial_tests/test_payment_idempotency.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    print(result.stdout)
    if result.returncode != 1:
        print("Expected adversarial test to fail, but failure proof was not produced.")
        return 1
    if "FAILED demo/adversarial_tests" not in result.stdout or "assert 2 == 1" not in result.stdout:
        print("Test failed for an unexpected reason.")
        return 1
    print("PROOF CONFIRMED: timeout-after-success creates duplicate payment side effect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
