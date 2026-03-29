#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
REPORT_CACHE_DIR = BACKEND_ROOT / "reports_cache"

DEFAULT_DOCS = [
    "docs/README.md",
    "docs/USER_GUIDE.md",
    "docs/FEATURE_BROCHURE.md",
    "docs/SALES_DEMO_PLAYBOOK.md",
    "docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md",
    "docs/KPI_READINESS_RUNBOOK.md",
    "docs/VENDOR_SUPPORT_POLICY.md",
    "docs/operational-validation/REAL_DEVICE_ACCEPTANCE_RUNBOOK.md",
]

REPORT_SPECS: dict[str, tuple[Path, ...]] = {
    "reports/release-evidence.latest.json": (
        REPORT_CACHE_DIR / "release-evidence.latest.json",
    ),
    "reports/kpi-readiness-30d-latest.json": (
        PROJECT_ROOT / "docs" / "reports" / "kpi-readiness-30d-latest.json",
        REPORT_CACHE_DIR / "kpi-readiness-30d-latest.json",
    ),
    "reports/kpi-readiness-30d-latest.md": (
        PROJECT_ROOT / "docs" / "reports" / "kpi-readiness-30d-latest.md",
    ),
    "reports/vendor-support-matrix.latest.json": (
        PROJECT_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json",
        REPORT_CACHE_DIR / "vendor-support-matrix.latest.json",
    ),
    "reports/vendor-support-matrix.latest.md": (
        PROJECT_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.md",
    ),
    "reports/synthetic-validation-matrix.latest.json": (
        PROJECT_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.json",
        REPORT_CACHE_DIR / "synthetic-validation-matrix.latest.json",
    ),
    "reports/synthetic-validation-matrix.latest.md": (
        PROJECT_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.md",
    ),
    "reports/real-device-acceptance.latest.json": (
        PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance.latest.json",
    ),
    "reports/real-device-acceptance.latest.md": (
        PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance.latest.md",
    ),
    "reports/real-device-acceptance-checklist.latest.csv": (
        PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance-checklist.latest.csv",
    ),
}

DEMO_SCENARIOS = [
    {
        "id": "wow_plug_scan",
        "title": "Plug & Scan to Topology",
        "value_message": "A newly discovered environment turns into an actionable topology and candidate queue without manual drawing.",
        "proof_points": [
            "Discovery completes and candidate queue ranks actionable links first",
            "Topology opens directly from discovery workflow",
            "Operational KPI panel shows measured plug-and-scan metrics",
        ],
        "related_assets": [
            "docs/SALES_DEMO_PLAYBOOK.md",
            "reports/kpi-readiness-30d-latest.json",
        ],
    },
    {
        "id": "layered_visibility",
        "title": "L2/L3/BGP/VXLAN Visibility",
        "value_message": "The same topology view can pivot between physical and routed overlays without changing tools.",
        "proof_points": [
            "L3 and BGP filters isolate routed relationships",
            "VXLAN overlay mode highlights VTEPs, VNIs, and EVPN peers",
            "Hybrid mode shows cloud and on-prem nodes together",
        ],
        "related_assets": [
            "docs/SALES_DEMO_PLAYBOOK.md",
            "reports/vendor-support-matrix.latest.json",
        ],
    },
    {
        "id": "path_trace_diagnosis",
        "title": "Path Trace and One-Click Diagnosis",
        "value_message": "Operators can move from a failing path to structured diagnosis without leaving the workflow.",
        "proof_points": [
            "Path trace returns best-effort segments even with degraded links",
            "Diagnosis summarizes likely root cause and next actions",
            "Degraded hops and show-plan outputs remain visible in UI and API",
        ],
        "related_assets": [
            "docs/SALES_DEMO_PLAYBOOK.md",
            "reports/kpi-readiness-30d-latest.json",
        ],
    },
    {
        "id": "safe_change_automation",
        "title": "Compliance to Approval to Rollback",
        "value_message": "The product does not stop at visibility; it closes the loop with guarded change execution.",
        "proof_points": [
            "Compliance report exposes remediation automation plan",
            "Approval payload carries deploy guard and rollback context",
            "Change KPI evidence shows rollback and trace coverage",
        ],
        "related_assets": [
            "docs/AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md",
            "reports/kpi-readiness-30d-latest.md",
        ],
    },
    {
        "id": "operational_evidence",
        "title": "Operational Proof and Release Evidence",
        "value_message": "The demo can end on measurable proof instead of promises.",
        "proof_points": [
            "Vendor support matrix quantifies fixture-backed readiness",
            "Synthetic validation matrix proves deterministic regression coverage",
            "Release evidence summarizes current accepted gates and remaining blockers",
        ],
        "related_assets": [
            "reports/release-evidence.latest.json",
            "reports/synthetic-validation-matrix.latest.json",
            "reports/real-device-acceptance.latest.json",
        ],
    },
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _copy_file(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def _copy_optional_reports(out_dir: Path) -> dict[str, str]:
    copied: dict[str, str] = {}
    for arcname, candidates in REPORT_SPECS.items():
        src = _first_existing(candidates)
        if src is None:
            continue
        dst = out_dir / arcname
        _copy_file(src, dst)
        copied[arcname] = str(src)
    return copied


def _copy_docs(out_dir: Path, docs: list[str]) -> list[str]:
    copied: list[str] = []
    for rel in docs:
        src = (PROJECT_ROOT / rel).resolve()
        if not src.exists():
            continue
        dst = out_dir / rel
        _copy_file(src, dst)
        copied.append(rel)
    return copied


def _unwrap_kpi_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    nested = payload.get("payload")
    return nested if isinstance(nested, dict) else payload


def build_demo_manifest(
    *,
    release_evidence: dict | None,
    kpi_readiness: dict | None,
    vendor_support: dict | None,
    synthetic_validation: dict | None,
    real_device_acceptance: dict | None,
) -> dict:
    release_summary = (release_evidence or {}).get("summary") if isinstance((release_evidence or {}).get("summary"), dict) else {}
    kpi_payload = _unwrap_kpi_payload(kpi_readiness)
    kpi_status = (kpi_payload.get("readiness") or {}).get("status") if isinstance(kpi_payload.get("readiness"), dict) else None
    vendor_summary = (vendor_support or {}).get("summary") if isinstance((vendor_support or {}).get("summary"), dict) else {}
    acceptance_summary = (real_device_acceptance or {}).get("summary") if isinstance((real_device_acceptance or {}).get("summary"), dict) else {}
    synthetic_summary = (synthetic_validation or {}).get("summary") if isinstance((synthetic_validation or {}).get("summary"), dict) else {}
    return {
        "generated_at": _now_iso(),
        "product_name": "NetSphere",
        "audiences": ["MSP", "Enterprise Network Ops", "Security Operations", "Hybrid Cloud Operations"],
        "current_proof": {
            "release_overall_status": str(release_summary.get("overall_status") or "unavailable"),
            "accepted_gates": int(release_summary.get("accepted_gates") or 0),
            "total_gates": int(release_summary.get("total_gates") or 0),
            "kpi_status": str(kpi_status or "unknown"),
            "vendor_full_count": int((((vendor_summary.get("readiness") or {}).get("full")) or 0)),
            "vendor_basic_or_better_count": int(
                (((vendor_summary.get("readiness") or {}).get("full")) or 0)
                + (((vendor_summary.get("readiness") or {}).get("extended")) or 0)
                + (((vendor_summary.get("readiness") or {}).get("basic")) or 0)
            ),
            "synthetic_overall_pass": bool((synthetic_validation or {}).get("overall_pass")),
            "synthetic_scenarios": int(synthetic_summary.get("checked_fixture_scenarios") or 0),
            "real_device_wave_1": int((((acceptance_summary.get("wave_counts") or {}).get("wave_1")) or 0)),
        },
        "demo_tracks": list(DEMO_SCENARIOS),
        "close_plan": [
            "Use synthetic or staged dataset for the live demo path.",
            "Close with release evidence and vendor support summary.",
            "Offer real-device acceptance checklist for target vendor family as the next step.",
        ],
    }


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_markdown(path: Path, payload: dict) -> None:
    proof = payload.get("current_proof") if isinstance(payload.get("current_proof"), dict) else {}
    lines = [
        "# Sales Demo Brief",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Release evidence: {proof.get('release_overall_status')} ({proof.get('accepted_gates')}/{proof.get('total_gates')} gates)",
        f"- KPI readiness: {proof.get('kpi_status')}",
        f"- Vendor support full: {proof.get('vendor_full_count')}",
        f"- Synthetic scenarios: {proof.get('synthetic_scenarios')}",
        f"- Real-device wave 1 targets: {proof.get('real_device_wave_1')}",
        "",
        "## Demo tracks",
        "",
    ]
    for scenario in list(payload.get("demo_tracks") or []):
        lines.extend(
            [
                f"### {scenario.get('title')}",
                "",
                str(scenario.get("value_message") or ""),
                "",
                "Proof points:",
                *[f"- {item}" for item in list(scenario.get("proof_points") or [])],
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def package_sales_demo_bundle(
    *,
    out_dir: Path,
    zip_name: str,
    docs: list[str],
) -> tuple[Path, Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied_docs = _copy_docs(out_dir, docs)
    copied_reports = _copy_optional_reports(out_dir)

    release_evidence = _read_json(_first_existing(REPORT_SPECS["reports/release-evidence.latest.json"]) or Path())
    kpi_readiness = _read_json(_first_existing(REPORT_SPECS["reports/kpi-readiness-30d-latest.json"]) or Path())
    vendor_support = _read_json(_first_existing(REPORT_SPECS["reports/vendor-support-matrix.latest.json"]) or Path())
    synthetic_validation = _read_json(_first_existing(REPORT_SPECS["reports/synthetic-validation-matrix.latest.json"]) or Path())
    real_device_acceptance = _read_json(_first_existing(REPORT_SPECS["reports/real-device-acceptance.latest.json"]) or Path())

    manifest = build_demo_manifest(
        release_evidence=release_evidence,
        kpi_readiness=kpi_readiness,
        vendor_support=vendor_support,
        synthetic_validation=synthetic_validation,
        real_device_acceptance=real_device_acceptance,
    )
    manifest_path = out_dir / "manifest.json"
    brief_path = out_dir / "demo-brief.md"
    _write_json(manifest_path, manifest)
    _write_markdown(brief_path, manifest)

    readme = out_dir / "README.txt"
    readme.write_text(
        "\n".join(
            [
                "NetSphere Sales Demo Package",
                "============================",
                "",
                "Contents:",
                *[f"- {doc}" for doc in copied_docs],
                *[f"- {name}" for name in sorted(copied_reports.keys())],
                "- manifest.json",
                "- demo-brief.md",
                "",
                "Use the playbook first, then close the demo with release evidence and the acceptance plan.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    zip_path = out_dir.parent / zip_name
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(out_dir)))
    return out_dir, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package a sales/demo bundle with playbook, proof artifacts, and scenario brief.")
    parser.add_argument("--out-dir", default="dist/sales-demo-package", help="Output directory for the demo bundle")
    parser.add_argument("--zip-name", default="sales-demo-package.zip", help="Zip filename under the output parent directory")
    parser.add_argument("--doc", action="append", default=[], help="Additional project-relative docs to include")
    args = parser.parse_args()

    docs = list(DEFAULT_DOCS)
    docs.extend(str(item).strip() for item in (args.doc or []) if str(item).strip())
    out_dir, zip_path = package_sales_demo_bundle(
        out_dir=(PROJECT_ROOT / args.out_dir).resolve(),
        zip_name=str(args.zip_name or "sales-demo-package.zip").strip(),
        docs=docs,
    )

    print(f"Packaged sales demo docs: {len(docs)}")
    print(f"Bundle directory: {out_dir}")
    print(f"Bundle zip: {zip_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
