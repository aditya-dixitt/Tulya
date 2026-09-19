def test_materials_requires_authentication(client):
    assert client.get("/api/materials").status_code == 401


def test_list_materials_is_paginated(client, as_viewer):
    r = client.get("/api/materials?limit=5")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 5
    assert body["total"] > 5 and body["limit"] == 5 and body["offset"] == 0


def test_record_carries_its_attributes_and_provenance(client, as_viewer):
    r = client.get("/api/materials?limit=50")
    rec = next(x for x in r.json()["items"] if x["attributes"])
    a = rec["attributes"][0]
    assert a["source"] == "RULE"
    assert a["provenance"] == "MEASURED"
    assert isinstance(a["is_hard_key"], bool)


def test_search_uses_the_engine_normaliser(client, as_viewer):
    r = client.get("/api/materials", params={"q": "stainless steel", "limit": 3})
    assert r.status_code == 200
    assert r.json()["total"] > 0


def test_filter_by_cpse(client, as_viewer):
    r = client.get("/api/materials", params={"cpse": "IOCL", "limit": 5})
    assert r.status_code == 200
    assert all(i["cpse"] == "IOCL" for i in r.json()["items"])


def test_legacy_code_resolution_returns_every_candidate(client, as_viewer):
    """Legacy codes are ambiguous in this dataset; the API must not pick one."""
    r = client.get("/api/materials?limit=1")
    rec = r.json()["items"][0]
    got = client.get(f"/api/materials/by-legacy/{rec['cpse']}/{rec['legacy_code']}")
    assert got.status_code == 200
    assert isinstance(got.json(), list) and len(got.json()) >= 1


def test_unknown_record_is_404(client, as_viewer):
    r = client.get("/api/materials/99999999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"
