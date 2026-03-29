
import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Fix Python Path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from datetime import datetime
from app.models.device import Device, Link, Interface
from app.services.syslog_service import SyslogProtocol
from app.services import realtime_event_bus as reb

# Mock DB Session
@pytest.fixture
def mock_db_session():
    session = MagicMock()
    return session

def test_syslog_link_down_event_publishes_to_bus(mock_db_session):
    async def _run():
        # Setup Data
        device = Device(id=1, name="Core-SW", ip_address="192.168.1.1", device_type="cisco_ios")
        neighbor = Device(id=2, name="Access-SW", ip_address="192.168.1.2", device_type="cisco_ios")
        
        interface = Interface(id=50, device_id=1, name="GigabitEthernet1/0/1", status="up")

        # Existing Link
        link = Link(
            id=100,
            source_device_id=1,
            source_interface_name="GigabitEthernet1/0/1",
            target_device_id=2,
            target_interface_name="GigabitEthernet0/1",
            protocol="LLDP",
            status="up"
        )

        # Mock DB Query Results
        # Sequence of .first() calls:
        # 1. Device lookup (syslog_service.py line 42)
        # 2. Interface lookup (syslog_service.py line 142)
        # 3. Issue lookup (syslog_service.py line 249)
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [device, interface, None] + [None]*10
        
        # 2. Link lookup (.all())
        # We need to mock the complex filter logic in syslog_service.py
        # It queries Link filtering by source OR target device_id
        mock_db_session.query.return_value.filter.return_value.all.return_value = [link]

        # Patch SessionLocal to return our mock session
        with patch("app.services.syslog_service.SessionLocal", return_value=mock_db_session):
            # Patch realtime_event_bus.publish to capture events
            with patch.object(reb.realtime_event_bus, "publish") as mock_publish:
                
                protocol = SyslogProtocol()
                
                # Simulate Syslog Message: Interface Down
                # %LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down
                syslog_msg = "<187>80: *Feb 10 17:55:01.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down"
                
                await protocol.process_log("192.168.1.1", syslog_msg)
                
                # Verify DB updates
                assert interface.status == "down" # Interface should be updated
                assert link.status == "down" # Link should be updated
                assert mock_db_session.commit.called
                
                # Verify Event Bus Publish
                mock_publish.assert_called_once()
                args, kwargs = mock_publish.call_args
                event_name = args[0]
                data = args[1]
                
                assert event_name == "link_update"
                assert data["device_id"] == 1
                assert data["state"] == "down"
                # assert data["protocol"] == "LLDP" # Syslog generic interface update doesn't carry protocol
                assert 100 in data["link_ids"]

    asyncio.run(_run())

def test_syslog_link_up_event_publishes_to_bus(mock_db_session):
    async def _run():
        # Setup Data
        device = Device(id=1, name="Core-SW", ip_address="192.168.1.1")
        interface = Interface(id=50, device_id=1, name="GigabitEthernet1/0/1", status="down")
        
        link = Link(
            id=100,
            source_device_id=1,
            source_interface_name="GigabitEthernet1/0/1",
            target_device_id=2,
            target_interface_name="GigabitEthernet0/1",
            protocol="LLDP",
            status="down"
        )

        # Mock DB Query Results
        # Sequence of .first() calls:
        # 1. Device lookup (syslog_service.py line 42)
        # 2. Interface lookup (syslog_service.py line 142)
        # 3. Issue lookup (syslog_service.py line 249)
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [device, interface, None] + [None]*10
        mock_db_session.query.return_value.filter.return_value.all.return_value = [link]

        with patch("app.services.syslog_service.SessionLocal", return_value=mock_db_session):
            with patch.object(reb.realtime_event_bus, "publish") as mock_publish:
                protocol = SyslogProtocol()
                
                # Simulate Syslog Message: Interface Up
                # %LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to up
                syslog_msg = "<187>80: *Feb 10 17:55:01.000: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to up"
                
                await protocol.process_log("192.168.1.1", syslog_msg)
                
                assert interface.status == "up"
                assert link.status == "up"
                
                mock_publish.assert_called_once()
                args, _ = mock_publish.call_args
                assert args[0] == "link_update"
                assert args[1]["state"] == "up"

    asyncio.run(_run())
