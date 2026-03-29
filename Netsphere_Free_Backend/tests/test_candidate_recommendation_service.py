import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.topology_candidate import TopologyNeighborCandidate
from app.services.candidate_recommendation_service import CandidateRecommendationService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_recommendations_rank_name_equal_over_prefix(db):
    job = DiscoveryJob(cidr="10.0.0.0/30", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    d1 = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.10", hostname="sw01.domain.local", vendor="Cisco", model="", os_version="", snmp_status="reachable", status="new")
    d2 = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.11", hostname="sw0100", vendor="Cisco", model="", os_version="", snmp_status="reachable", status="new")
    db.add_all([d1, d2])
    db.commit()

    cand = TopologyNeighborCandidate(discovery_job_id=job.id, source_device_id=1, neighbor_name="SW-01", mgmt_ip=None, status="unmatched")
    db.add(cand)
    db.commit()
    db.refresh(cand)

    recs = CandidateRecommendationService.recommend_for_candidate(db, cand, limit=5)
    assert recs
    assert recs[0]["ip_address"] == "10.0.0.10"
    assert recs[0]["match_band"] == "high"
    assert recs[0]["action_ready"] is True
