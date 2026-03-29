import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.settings import SystemSetting

def test_read_devices_empty(client: TestClient, normal_user_token):
    response = client.get("/api/v1/devices/", headers=normal_user_token)
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == []

def test_create_device(client: TestClient, admin_user_token, db: Session):
    # 1. Create a new device
    payload = {
        "name": "test-device-01",
        "ip_address": "192.168.1.1",
        "device_type": "cisco_ios",
        "ssh_username": "admin",
        "ssh_password": "password",
        "snmp_community": "public"
    }
    response = client.post("/api/v1/devices/", json=payload, headers=admin_user_token)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == payload["name"]
    assert data["ip_address"] == payload["ip_address"]
    assert "id" in data

    # 2. Verify in DB
    device = db.query(Device).filter(Device.name == "test-device-01").first()
    assert device is not None
    assert device.ip_address == "192.168.1.1"

def test_read_device_detail(client: TestClient, normal_user_token, db: Session):
    # Setup: Create a device directly in DB
    device = Device(
        name="detail-test-device",
        ip_address="10.0.0.1",
        device_type="juniper_junos",
        status="online"
    )
    db.add(device)
    db.commit()

    response = client.get(f"/api/v1/devices/{device.id}", headers=normal_user_token)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "detail-test-device"
    assert data["status"] == "online"

def test_update_device(client: TestClient, admin_user_token, db: Session):
    # Setup
    device = Device(name="update-target", ip_address="10.0.0.2")
    db.add(device)
    db.commit()

    # Update
    payload = {"name": "updated-name", "location": "Seoul DC"}
    response = client.put(f"/api/v1/devices/{device.id}", json=payload, headers=admin_user_token)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "updated-name"
    assert data["location"] == "Seoul DC"

    # Verify DB
    db.refresh(device)
    assert device.name == "updated-name"

def test_delete_device(client: TestClient, admin_user_token, db: Session):
    # Setup
    device = Device(name="delete-target", ip_address="10.0.0.3")
    db.add(device)
    db.commit()

    # Delete
    response = client.delete(f"/api/v1/devices/{device.id}", headers=admin_user_token)
    assert response.status_code == 200
    
    # Verify Gone
    check = db.query(Device).filter(Device.id == device.id).first()
    assert check is None

def test_analytics_n_plus_one_optimization(client: TestClient, normal_user_token, db: Session):
    """
    Test the N+1 optimization logic in get_analytics_data.
    It should return latest metrics for multiple devices correctly.
    """
    from app.models.device import SystemMetric
    from datetime import datetime
    
    # Setup: 2 Devices
    d1 = Device(name="d1", ip_address="1.1.1.1", status="online")
    d2 = Device(name="d2", ip_address="2.2.2.2", status="online")
    db.add_all([d1, d2])
    db.commit()
    
    # Add metrics
    now = datetime.now()
    # Old metric for d1
    m1_old = SystemMetric(device_id=d1.id, timestamp=now, cpu_usage=10, memory_usage=10)
    # New metric for d1
    m1_new = SystemMetric(device_id=d1.id, timestamp=now, cpu_usage=50, memory_usage=50)
    # Metric for d2
    m2 = SystemMetric(device_id=d2.id, timestamp=now, cpu_usage=80, memory_usage=80)
    
    db.add_all([m1_old, m1_new, m2])
    db.commit()
    
    response = client.get("/api/v1/devices/analytics?range=1h", headers=normal_user_token)
    assert response.status_code == 200
    data = response.json()["data"]
    
    top_devices = data["topDevices"]
    # Should contain d1(50%) and d2(80%)
    # Sort order is descending by usage, so d2 first
    assert len(top_devices) == 2
    assert top_devices[0]["name"] == "d2"
    assert top_devices[0]["usage"] == 80.0
    assert top_devices[1]["name"] == "d1"
    assert top_devices[1]["usage"] == 50.0 # Should pick the max timestamp one, not random
