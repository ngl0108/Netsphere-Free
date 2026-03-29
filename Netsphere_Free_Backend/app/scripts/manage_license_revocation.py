from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return []
        parsed = json.loads(raw)
    except Exception:
        return []
    if isinstance(parsed, list):
        out: list[dict[str, Any]] = []
        for item in parsed:
            jti = str(item or "").strip()
            if jti:
                out.append({"jti": jti, "reason": "revoked_by_file"})
        return out
    if not isinstance(parsed, dict):
        return []
    rows = parsed.get("revoked")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, str):
            jti = row.strip()
            if jti:
                out.append({"jti": jti, "reason": "revoked_by_file"})
            continue
        if not isinstance(row, dict):
            continue
        jti = str(row.get("jti") or "").strip()
        if not jti:
            continue
        out.append(
            {
                "jti": jti,
                "reason": str(row.get("reason") or "revoked_by_file").strip() or "revoked_by_file",
                "revoked_at": str(row.get("revoked_at") or "").strip() or None,
                "revoked_by": str(row.get("revoked_by") or "").strip() or None,
            }
        )
    return out


def _save_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"revoked": rows}, ensure_ascii=False, indent=2), encoding="utf-8")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage NetSphere license revocation list.")
    parser.add_argument(
        "--file",
        default="license_revocations.json",
        help="Revocation list path (default: license_revocations.json)",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["list", "revoke", "unrevoke"],
        help="Operation to perform",
    )
    parser.add_argument("--jti", default="", help="License token jti for revoke/unrevoke")
    parser.add_argument("--reason", default="manual_revoke", help="Revoke reason")
    parser.add_argument("--actor", default="ops_admin", help="Revoked by actor")
    args = parser.parse_args()

    path = Path(args.file)
    rows = _load_rows(path)

    if args.action == "list":
        _print_json({"file": str(path), "count": len(rows), "revoked": rows})
        return 0

    jti = str(args.jti or "").strip()
    if not jti:
        raise ValueError("--jti is required for revoke/unrevoke")

    if args.action == "revoke":
        found = False
        for row in rows:
            if str(row.get("jti") or "").strip() == jti:
                row["reason"] = str(args.reason or "manual_revoke").strip() or "manual_revoke"
                row["revoked_by"] = str(args.actor or "ops_admin").strip() or "ops_admin"
                row["revoked_at"] = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if not found:
            rows.append(
                {
                    "jti": jti,
                    "reason": str(args.reason or "manual_revoke").strip() or "manual_revoke",
                    "revoked_by": str(args.actor or "ops_admin").strip() or "ops_admin",
                    "revoked_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        _save_rows(path, rows)
        _print_json({"ok": True, "action": "revoke", "jti": jti, "count": len(rows)})
        return 0

    kept = [row for row in rows if str(row.get("jti") or "").strip() != jti]
    removed = len(kept) != len(rows)
    if removed:
        _save_rows(path, kept)
    _print_json({"ok": True, "action": "unrevoke", "jti": jti, "removed": removed, "count": len(kept)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
