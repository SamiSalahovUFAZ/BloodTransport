from src.accounts import AccountRepository
from src.app import create_app
from src.auth import PASSWORD_HASH_METHOD
from werkzeug.security import generate_password_hash


def test_workspace_tools_follow_transport_permissions(tmp_path):
    database = tmp_path / "tools.sqlite3"
    app = create_app(database)
    accounts = AccountRepository(database)
    password = "demo-workspace-password"
    accounts.create("Sam", generate_password_hash(password, method=PASSWORD_HASH_METHOD), "dispatcher", None)
    accounts.create("Lee", "unused", "courier", None)
    dispatcher = app.test_client()
    with dispatcher.session_transaction() as session:
        session.update(username="Sam", csrf_token="test-token")
    headers = {"X-CSRF-Token": "test-token"}
    base = "/api/transport-requests"
    job = dispatcher.post(base, json={
        "sample_code": "LABEL-23", "sample_type": "serum", "origin": "Clinic",
        "destination": "Central Lab", "pickup_at": "2030-08-10T10:00:00Z",
    }, headers=headers).json
    tracking = f"/tracking/{job['id']}"
    label = f"/tools/labels/{job['id']}"
    issue = dispatcher.post(base + f"/{job['id']}/incidents", json={
        "description": "Pickup desk relocated.",
    }, headers=headers).json

    assert b"Shift planner" in dispatcher.get("/tools").data
    assert b"LABEL-23" in dispatcher.get("/tools/planner").data
    assert b"LABEL-23" not in dispatcher.get("/tools/labels?q=wrong").data
    assert b"Print label" in dispatcher.get(label).data
    qr = dispatcher.get(label + "/qr.svg")
    assert qr.status_code == 200 and qr.mimetype == "image/svg+xml"
    assert b"<svg" in qr.data
    assert b"Pickup desk relocated." in dispatcher.get("/tools/incidents").data
    resolved = dispatcher.patch(base + f"/{job['id']}/incidents/{issue['id']}/resolve", headers=headers)
    assert resolved.status_code == 200
    assert b"Pickup desk relocated." not in dispatcher.get("/tools/incidents").data
    assert b"Pickup desk relocated." in dispatcher.get("/tools/incidents?status=resolved").data

    courier = app.test_client()
    with courier.session_transaction() as session:
        session["username"] = "Lee"
    for path in (tracking, label, label + "/qr.svg"):
        assert courier.get(path).status_code == 404
    for path in ("/tools/planner", "/tools/labels", "/tools/incidents?status=all"):
        assert b"LABEL-23" not in courier.get(path).data

    scanner = app.test_client()
    assert scanner.get(tracking).location == "/login"
    scanner.get("/login")
    with scanner.session_transaction() as session:
        token = session["csrf_token"]
    response = scanner.post("/login", data={
        "username": "Sam", "password": password, "csrf_token": token,
    }, follow_redirects=True)
    assert response.request.path == tracking and b"LABEL-23" in response.data
