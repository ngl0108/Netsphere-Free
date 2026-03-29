from app.models.discovery import DiscoveryJob


def test_discovery_stream_requires_auth(client, db):
    job = DiscoveryJob(cidr="10.66.0.0/24", status="completed", logs="")
    db.add(job)
    db.commit()

    res = client.get(f"/api/v1/discovery/jobs/{job.id}/stream")
    assert res.status_code == 401


def test_discovery_stream_accepts_query_token(client, normal_user_token, db):
    job = DiscoveryJob(cidr="10.67.0.0/24", status="completed", logs="")
    db.add(job)
    db.commit()

    token = str(normal_user_token.get("Authorization", "")).split(" ", 1)[1]
    res = client.get(f"/api/v1/discovery/jobs/{job.id}/stream?access_token={token}")
    assert res.status_code == 200
    assert "Could not validate credentials" not in res.text
    assert "Not authenticated" not in res.text
