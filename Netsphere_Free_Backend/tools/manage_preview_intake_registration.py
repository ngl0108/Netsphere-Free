import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.models import preview_collector_registration  # noqa: F401,E402
from app.services.preview_edition_service import PreviewEditionService  # noqa: E402


def _dump(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_list(_args: argparse.Namespace) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        rows = PreviewEditionService.list_intake_registrations(db)
        _dump({"count": len(rows), "registrations": rows})
        return 0
    finally:
        db.close()


def cmd_create(args: argparse.Namespace) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        payload = PreviewEditionService.create_intake_registration(
            db,
            label=args.label,
            issued_to=args.issued_to or "",
            notes=args.notes or "",
            created_by=args.created_by or "",
        )
        _dump(payload)
        return 0
    finally:
        db.close()


def cmd_rotate(args: argparse.Namespace) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        payload = PreviewEditionService.rotate_intake_registration(
            db,
            collector_id=args.collector_id,
            notes=args.notes or "",
            rotated_by=args.rotated_by or "",
        )
        _dump(payload)
        return 0
    finally:
        db.close()


def cmd_revoke(args: argparse.Namespace) -> int:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        payload = PreviewEditionService.revoke_intake_registration(
            db,
            collector_id=args.collector_id,
        )
        _dump(payload)
        return 0
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage preview intake collector registrations for hosted preview deployments."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List issued collector registrations")
    list_parser.set_defaults(func=cmd_list)

    create_parser = sub.add_parser("create", help="Create a new collector registration")
    create_parser.add_argument("--label", required=True, help="Human-readable customer/build label")
    create_parser.add_argument("--issued-to", default="", help="Customer name, email, or account identifier")
    create_parser.add_argument("--notes", default="", help="Free-form notes")
    create_parser.add_argument("--created-by", default="cli", help="Issuer label")
    create_parser.set_defaults(func=cmd_create)

    rotate_parser = sub.add_parser("rotate", help="Rotate the intake token for an existing collector")
    rotate_parser.add_argument("--collector-id", required=True, help="Collector registration id")
    rotate_parser.add_argument("--notes", default="", help="Optional updated notes")
    rotate_parser.add_argument("--rotated-by", default="cli", help="Rotator label")
    rotate_parser.set_defaults(func=cmd_rotate)

    revoke_parser = sub.add_parser("revoke", help="Revoke an existing collector registration")
    revoke_parser.add_argument("--collector-id", required=True, help="Collector registration id")
    revoke_parser.set_defaults(func=cmd_revoke)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
