def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_reports_database_and_engine(client):
    r = client.get("/api/ready")
    body = r.json()
    assert body["database"]["ok"] is True
    # the engine must name the backends that would actually run
    eng = body["engine"]
    assert eng["index"]["backend"] in ("faiss-flatip", "numpy-exact")
    assert eng["fuzzy"]["backend"] in ("rapidfuzz", "difflib")


def test_request_id_is_returned(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Request-ID")


def test_system_status_needs_admin(client, as_viewer):
    r = client.get("/api/system/status")
    assert r.status_code == 403
    assert r.json()["detail"]["required"] == "admin"
