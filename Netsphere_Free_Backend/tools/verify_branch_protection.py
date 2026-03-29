#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Iterable

import requests


def _extract_required_contexts(payload: dict) -> set[str]:
    required = payload.get("required_status_checks") or {}
    contexts = required.get("contexts") or []
    checks = required.get("checks") or []
    result: set[str] = set()
    for item in contexts:
        value = str(item or "").strip()
        if value:
            result.add(value)
    for item in checks:
        if isinstance(item, dict):
            value = str(item.get("context") or "").strip()
        else:
            value = str(item or "").strip()
        if value:
            result.add(value)
    return result


def _print_result(ok: bool, message: str, extra: dict | None = None) -> None:
    payload = {"ok": bool(ok), "message": message}
    if extra:
        payload["details"] = extra
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def verify_branch_protection(
    *,
    repo: str,
    branch: str,
    token: str,
    required_checks: Iterable[str],
    require_strict: bool,
    require_admin_enforced: bool,
) -> int:
    owner_repo = str(repo or "").strip()
    if not owner_repo or "/" not in owner_repo:
        _print_result(False, "Invalid --repo. Expected format: owner/repo")
        return 2

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{owner_repo}/branches/{branch}/protection"
    resp = requests.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
        _print_result(
            False,
            "Failed to fetch branch protection",
            {"status_code": resp.status_code, "response": resp.text[:500]},
        )
        return 2

    payload = resp.json() if resp.content else {}
    required = {str(x).strip() for x in required_checks if str(x or "").strip()}
    configured = _extract_required_contexts(payload)
    missing = sorted(required - configured)

    strict_ok = True
    strict_value = bool((payload.get("required_status_checks") or {}).get("strict"))
    if require_strict and not strict_value:
        strict_ok = False

    admins_ok = True
    admins_enabled = bool((payload.get("enforce_admins") or {}).get("enabled"))
    if require_admin_enforced and not admins_enabled:
        admins_ok = False

    ok = (len(missing) == 0) and strict_ok and admins_ok
    details = {
        "repo": owner_repo,
        "branch": branch,
        "required_checks": sorted(required),
        "configured_checks": sorted(configured),
        "missing_checks": missing,
        "strict_enabled": strict_value,
        "admin_enforced": admins_enabled,
    }
    if ok:
        _print_result(True, "Branch protection requirements satisfied", details)
        return 0

    message_parts = []
    if missing:
        message_parts.append(f"missing required checks: {', '.join(missing)}")
    if not strict_ok:
        message_parts.append("strict status checks is disabled")
    if not admins_ok:
        message_parts.append("enforce_admins is disabled")
    _print_result(False, "; ".join(message_parts) or "Branch protection requirements not satisfied", details)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify GitHub branch protection required checks for NetSphere release gate."
    )
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/repo format")
    parser.add_argument("--branch", default="main", help="Branch name (default: main)")
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN", ""),
        help="GitHub token (default: env GITHUB_TOKEN)",
    )
    parser.add_argument(
        "--required-check",
        action="append",
        default=["Release Gate"],
        help="Required status check context. Repeat for multiple checks.",
    )
    parser.add_argument(
        "--require-strict",
        action="store_true",
        help="Fail when strict status checks (up-to-date branch) is not enabled.",
    )
    parser.add_argument(
        "--require-admin-enforced",
        action="store_true",
        help="Fail when enforce_admins is not enabled.",
    )
    args = parser.parse_args()

    token = str(args.token or "").strip()
    if not token:
        _print_result(False, "Missing GitHub token. Set --token or GITHUB_TOKEN.")
        return 2

    return verify_branch_protection(
        repo=args.repo,
        branch=args.branch,
        token=token,
        required_checks=args.required_check,
        require_strict=bool(args.require_strict),
        require_admin_enforced=bool(args.require_admin_enforced),
    )


if __name__ == "__main__":
    raise SystemExit(main())
