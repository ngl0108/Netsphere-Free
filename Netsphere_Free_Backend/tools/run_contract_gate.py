from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "Netsphere_Free_Backend"
FRONTEND_ROOT = REPO_ROOT / "Netsphere_Free_Frontend"


def _run(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    print(f"[gate] ({cwd.name}) $ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run API/OpenAPI contract gates for backend+frontend."
    )
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-backend", action="store_true")
    args = parser.parse_args()

    env = dict(os.environ)

    if not args.skip_backend:
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/contracts/test_openapi_snapshot_contract.py",
                "tests/contracts/test_frontend_api_contract.py",
                "-q",
            ],
            cwd=BACKEND_ROOT,
            env=env,
        )

    if not args.skip_frontend:
        _run(["node", "scripts/check-api-contract.mjs"], cwd=FRONTEND_ROOT, env=env)

    print("[gate] Contract gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
