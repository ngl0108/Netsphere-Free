import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.topology_link_service import TopologyLinkService


def test_normalize_link_orders_by_device_id():
    a = TopologyLinkService._normalize_link(10, "Gi0/1", 20, "Gi0/2")
    assert a == (10, "Gi0/1", 20, "Gi0/2")

    b = TopologyLinkService._normalize_link(20, "Gi0/2", 10, "Gi0/1")
    assert b == (10, "Gi0/1", 20, "Gi0/2")
