from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "Netsphere_Free_Backend"
FRONTEND_ROOT = REPO_ROOT / "Netsphere_Free_Frontend"


def _run(cmd: list[str], cwd: Path, retries: int = 0) -> None:
    run_cmd = cmd
    if os.name == "nt":
        run_cmd = ["cmd", "/c", *cmd]
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(retries + 1):
        print(f"[quality-gate] ({cwd.name}) $ {' '.join(run_cmd)}")
        try:
            subprocess.run(run_cmd, cwd=str(cwd), env=dict(os.environ), check=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt >= retries:
                raise
            print(f"[quality-gate] retrying command ({attempt + 1}/{retries})...")
    if last_error:
        raise last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local quality gate (contract/i18n/build/e2e).")
    parser.add_argument("--skip-e2e", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-parser-benchmark", action="store_true")
    parser.add_argument("--skip-synthetic-matrix", action="store_true")
    parser.add_argument(
        "--synthetic-profile",
        choices=("ci", "local", "release"),
        default="ci",
        help="Synthetic validation profile to run before frontend checks.",
    )
    args = parser.parse_args()

    _run([sys.executable, "tools/run_contract_gate.py"], cwd=BACKEND_ROOT)
    if not args.skip_synthetic_matrix:
        _run(
            [
                sys.executable,
                "tools/run_synthetic_validation_matrix.py",
                "--profile",
                args.synthetic_profile,
                "--fail-on-unhealthy",
            ],
            cwd=BACKEND_ROOT,
        )
    if not args.skip_parser_benchmark:
        _run([sys.executable, "tools/run_vendor_parser_benchmark.py"], cwd=BACKEND_ROOT)
        _run([sys.executable, "tools/export_vendor_support_matrix.py"], cwd=BACKEND_ROOT)
    _run([sys.executable, "tools/build_release_evidence_cache.py"], cwd=BACKEND_ROOT)
    _run(["npm.cmd", "run", "contract:api"], cwd=FRONTEND_ROOT)
    _run(["npm.cmd", "run", "i18n:audit:strict"], cwd=FRONTEND_ROOT)

    if not args.skip_build:
        _run(["npm.cmd", "run", "build"], cwd=FRONTEND_ROOT, retries=1)

    if not args.skip_e2e:
        _run(["npm.cmd", "run", "e2e:ops"], cwd=FRONTEND_ROOT)

    print("[quality-gate] All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
