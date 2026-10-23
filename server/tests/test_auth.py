import pytest

pytestmark = pytest.mark.django_db


def test_register_login_refresh_me(api):
    status, body = api().post("/auth/register", {"email": "New@X.test", "password": "longpassword", "full_name": "New"})
    assert status == 201
    assert body["user"]["email"] == "new@x.test"

    status, body = api().post("/auth/register", {"email": "new@x.test", "password": "longpassword"})
    assert status == 409

    status, body = api().post("/auth/login", {"email": "new@x.test", "password": "wrong-password"})
    assert status == 401

    status, tokens = api().post("/auth/login", {"email": "new@x.test", "password": "longpassword"})
    assert status == 200

    client = api()
    client.headers["HTTP_AUTHORIZATION"] = f"Bearer {tokens['access']}"
    assert client.get("/auth/me")[1]["email"] == "new@x.test"

    # A refresh token can't be used as an access token, and vice versa.
    client.headers["HTTP_AUTHORIZATION"] = f"Bearer {tokens['refresh']}"
    assert client.get("/auth/me")[0] == 401
    assert api().post("/auth/refresh", {"refresh": tokens["access"]})[0] == 401
    assert api().post("/auth/refresh", {"refresh": tokens["refresh"]})[0] == 200


def test_short_password_rejected(api):
    status, body = api().post("/auth/register", {"email": "a@x.test", "password": "short"})
    assert status == 400


def test_api_requires_token(api):
    assert api().get("/classes")[0] == 401
