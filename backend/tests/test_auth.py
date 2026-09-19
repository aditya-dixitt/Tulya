import pytest


def test_login_sets_httponly_cookie_and_returns_csrf(client):
    r = client.post("/api/auth/login",
                    json={"username": "steward", "password": "steward123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "steward"
    assert body["csrf_token"]
    cookie = r.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie, "session cookie must not be readable from JS"


def test_bad_password_is_rejected_without_revealing_which_half(client):
    a = client.post("/api/auth/login", json={"username": "steward", "password": "wrong"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"]["message"] == b.json()["detail"]["message"]


def test_me_requires_a_session(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_after_login(client, as_steward):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "steward"


def test_logout_revokes_the_session(client, as_steward):
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("role,expected", [("viewer", 403), ("admin", 200)])
def test_role_hierarchy_is_enforced_server_side(client, role, expected):
    pw = {"viewer": "viewer123", "admin": "admin123"}[role]
    client.post("/api/auth/login", json={"username": role, "password": pw})
    assert client.get("/api/system/status").status_code == expected
