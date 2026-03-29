def test_topology_stream_requires_auth(client):
    res = client.get("/api/v1/topology/stream")
    assert res.status_code == 401
