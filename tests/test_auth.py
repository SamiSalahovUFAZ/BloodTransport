import hashlib
import sqlite3
from contextlib import closing

from src.app import create_app


def get_token(client, page):
    assert client.get(page).status_code == 200
    with client.session_transaction() as session:
        return session["csrf_token"]


def test_account_registration_login_and_logout_without_scrypt(tmp_path, monkeypatch):
    monkeypatch.delattr(hashlib, "scrypt", raising=False)
    database = tmp_path / "transport.sqlite3"
    client = create_app(database).test_client()
    assert client.get("/courier").location == "/login"
    assert client.get("/api/transport-requests").status_code == 401

    password = "test-password-42"
    registration = {
        "username": "Team.Member",
        "password": password,
        "confirm_password": password,
    }
    assert client.post("/register", data=registration).status_code == 400
    registration["csrf_token"] = get_token(client, "/register")
    assert client.post("/register", data=registration).location == "/"
    assert client.get("/").status_code == 200
    assert client.post("/api/transport-requests", json={}).status_code == 400

    with closing(sqlite3.connect(database)) as connection:
        (password_hash,) = connection.execute("SELECT password_hash FROM accounts").fetchone()
    assert password_hash.startswith("pbkdf2:sha256:") and password not in password_hash

    assert client.post("/logout").status_code == 400
    client.get("/")
    with client.session_transaction() as session:
        csrf_token = session["csrf_token"]
    assert client.post("/logout", data={"csrf_token": csrf_token}).location == "/login"
    assert client.get("/laboratory").location == "/login"

    restarted = create_app(database).test_client()
    token = get_token(restarted, "/login")
    credentials = {"username": "team.member", "password": password, "csrf_token": token}
    assert restarted.post("/login", data={**credentials, "password": "wrong"}).status_code == 401
    assert restarted.post("/login", data=credentials).location == "/"
    assert b"Team.Member" in restarted.get("/").data

    another_client = create_app(database).test_client()
    registration["username"] = "team.member"
    registration["csrf_token"] = get_token(another_client, "/register")
    assert another_client.post("/register", data=registration).status_code == 400
