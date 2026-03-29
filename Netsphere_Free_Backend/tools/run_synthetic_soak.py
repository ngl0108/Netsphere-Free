from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "test-data" / "synthetic" / "scenarios"


@dataclass
class SoakState:
    processed: int = 0
    duplicates: int = 0
    critical_seen: int = 0
    warnings_seen: int = 0
    info_seen: int = 0
    session_refresh_count: int = 0
    forced_logout_count: int = 0
    max_queue_depth: int = 0


def _load_scenario(name: str) -> dict[str, Any]:
    path = SCENARIO_ROOT / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Synthetic scenario not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _severity_counter(state: SoakState, severity: str) -> None:
    s = str(severity or "").strip().lower()
    if s == "critical":
        state.critical_seen += 1
    elif s in {"warn", "warning"}:
        state.warnings_seen += 1
    else:
        state.info_seen += 1


def run_soak(
    scenario_name: str,
    duration_sec: int,
    tick_ms: int,
    seed: int,
    session_timeout_sec: int,
    refresh_interval_sec: int,
) -> dict[str, Any]:
    scenario = _load_scenario(scenario_name)
    events = list(scenario.get("events") or [])
    if not events:
        events = [{"type": "synthetic_no_event", "severity": "info"}]

    rng = random.Random(seed)
    state = SoakState()
    dedupe = set()
    recent_fingerprints: list[str] = []
    queue_depth = 0
    last_activity_ts = time.monotonic()
    last_refresh_ts = time.monotonic()
    started = time.monotonic()

    while time.monotonic() - started < duration_sec:
        event = rng.choice(events)
        if recent_fingerprints and rng.random() < 0.08:
            fingerprint = rng.choice(recent_fingerprints)
        else:
            fingerprint = (
                f"{event.get('type')}:{event.get('device_id')}:{event.get('chunk_id')}:"
                f"{state.processed + 1}:{rng.randint(1000, 99999)}"
            )
            recent_fingerprints.append(fingerprint)
            if len(recent_fingerprints) > 256:
                recent_fingerprints.pop(0)

        if fingerprint in dedupe:
            state.duplicates += 1
        else:
            dedupe.add(fingerprint)

        state.processed += 1
        _severity_counter(state, str(event.get("severity") or "info"))

        queue_depth = max(0, queue_depth + rng.randint(-2, 4))
        state.max_queue_depth = max(state.max_queue_depth, queue_depth)

        now = time.monotonic()
        if now - last_refresh_ts >= refresh_interval_sec:
            state.session_refresh_count += 1
            last_refresh_ts = now
            last_activity_ts = now

        if now - last_activity_ts >= session_timeout_sec:
            # Simulate forced logout due to stale token.
            state.forced_logout_count += 1
            last_activity_ts = now

        time.sleep(max(0.0, tick_ms / 1000.0))

    elapsed = max(0.001, time.monotonic() - started)
    duplicate_ratio = state.duplicates / max(1, state.processed)
    throughput = state.processed / elapsed

    return {
        "scenario": scenario_name,
        "seed": seed,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_sec": duration_sec,
        "tick_ms": tick_ms,
        "session_timeout_sec": session_timeout_sec,
        "refresh_interval_sec": refresh_interval_sec,
        "metrics": {
            "processed_events": state.processed,
            "duplicates": state.duplicates,
            "duplicate_ratio": round(duplicate_ratio, 6),
            "critical_seen": state.critical_seen,
            "warnings_seen": state.warnings_seen,
            "info_seen": state.info_seen,
            "session_refresh_count": state.session_refresh_count,
            "forced_logout_count": state.forced_logout_count,
            "max_queue_depth": state.max_queue_depth,
            "throughput_eps": round(throughput, 2),
        },
        "pass": {
            "duplicate_ratio_under_0_2": duplicate_ratio <= 0.2,
            "forced_logout_zero": state.forced_logout_count == 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run synthetic soak/polling stability simulation.")
    parser.add_argument(
        "--scenario",
        default="normal",
        help="normal|large_scale|failure|security_incident|rollback_wave|hybrid_cloud|wireless_edge",
    )
    parser.add_argument("--duration-sec", type=int, default=60)
    parser.add_argument("--tick-ms", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260219)
    parser.add_argument("--session-timeout-sec", type=int, default=30)
    parser.add_argument("--refresh-interval-sec", type=int, default=10)
    parser.add_argument("--output", default=str(REPO_ROOT / "docs" / "reports" / "synthetic-soak-latest.json"))
    parser.add_argument("--fail-on-unhealthy", action="store_true")
    args = parser.parse_args()

    report = run_soak(
        scenario_name=args.scenario,
        duration_sec=max(1, int(args.duration_sec)),
        tick_ms=max(1, int(args.tick_ms)),
        seed=int(args.seed),
        session_timeout_sec=max(1, int(args.session_timeout_sec)),
        refresh_interval_sec=max(1, int(args.refresh_interval_sec)),
    )

    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.fail_on_unhealthy:
        if not all(report.get("pass", {}).values()):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
