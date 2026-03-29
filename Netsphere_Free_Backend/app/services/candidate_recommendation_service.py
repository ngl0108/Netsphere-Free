from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.discovery import DiscoveredDevice
from app.models.topology_candidate import TopologyNeighborCandidate


class CandidateRecommendationService:
    @staticmethod
    def _score_band(score: float) -> str:
        if score >= 0.9:
            return "high"
        if score >= 0.7:
            return "medium"
        return "low"

    @staticmethod
    def _normalize_name(name: str) -> str:
        s = (name or "").strip().lower()
        if not s:
            return ""
        if "." in s:
            s = s.split(".")[0]
        for ch in ("-", "_", " "):
            s = s.replace(ch, "")
        return s

    @staticmethod
    def _score(neighbor_name: str, discovered_hostname: str, discovered_ip: str, desired_ip: str) -> Tuple[float, str]:
        n_ip = (desired_ip or "").strip()
        d_ip = (discovered_ip or "").strip()
        if n_ip and d_ip and n_ip == d_ip:
            return 1.0, "ip_match"

        nn = CandidateRecommendationService._normalize_name(neighbor_name)
        dh = CandidateRecommendationService._normalize_name(discovered_hostname)
        if not nn or not dh:
            return 0.0, "missing_name"

        if nn == dh:
            return 0.9, "name_equal"
        if dh.startswith(nn) or nn.startswith(dh):
            return 0.7, "name_prefix"
        if len(nn) >= 4 and len(dh) >= 4 and (nn in dh or dh in nn):
            return 0.55, "name_contains"
        return 0.0, "no_match"

    @staticmethod
    def recommend_for_candidate(
        db: Session,
        candidate: TopologyNeighborCandidate,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        if not candidate or not candidate.discovery_job_id:
            return []

        neighbor_name = candidate.neighbor_name or ""
        desired_ip = (candidate.mgmt_ip or "").strip()

        items = (
            db.query(DiscoveredDevice)
            .filter(DiscoveredDevice.job_id == candidate.discovery_job_id)
            .filter(DiscoveredDevice.status != "ignored")
            .all()
        )

        scored: List[Tuple[float, str, DiscoveredDevice]] = []
        for d in items:
            score, reason = CandidateRecommendationService._score(neighbor_name, d.hostname or "", d.ip_address or "", desired_ip)
            if score <= 0:
                continue
            scored.append((score, reason, d))

        scored.sort(key=lambda x: (x[0], x[2].snmp_status == "reachable"), reverse=True)
        scored = scored[: max(1, min(int(limit or 5), 20))]

        result = []
        for score, reason, d in scored:
            band = CandidateRecommendationService._score_band(float(score))
            action_ready = bool(float(score) >= 0.85 or (float(score) >= 0.7 and str(d.snmp_status or "").strip().lower() == "reachable"))
            result.append(
                {
                    "discovered_id": d.id,
                    "ip_address": d.ip_address,
                    "hostname": d.hostname,
                    "vendor": d.vendor,
                    "model": d.model,
                    "os_version": d.os_version,
                    "snmp_status": d.snmp_status,
                    "status": d.status,
                    "score": float(score),
                    "reason": reason,
                    "match_band": band,
                    "action_ready": action_ready,
                }
            )
        return result
