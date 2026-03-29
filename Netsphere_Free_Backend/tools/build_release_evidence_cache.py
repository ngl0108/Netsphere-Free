from __future__ import annotations

from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.release_evidence_service import (  # noqa: E402
    build_release_evidence_summary,
    mirror_release_evidence_assets,
    write_release_evidence_cache,
)


def main() -> int:
    mirrored = mirror_release_evidence_assets()
    payload = build_release_evidence_summary()
    out = write_release_evidence_cache(payload)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    print(
        "Release evidence cache generated: "
        f"status={summary.get('overall_status', 'unavailable')} "
        f"accepted={summary.get('accepted_gates', 0)}/{summary.get('total_gates', 0)}"
    )
    print(
        "Mirrored assets: "
        f"reports={len(mirrored.get('reports') or [])} "
        f"runbooks={len(mirrored.get('runbooks') or [])}"
    )
    print(f"JSON cache: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
