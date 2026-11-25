from src.accounts import AccountRepository
from src.app import create_app


def test_role_scoped_sample_receipt(tmp_path):
    database = tmp_path / "transports.sqlite3"
    app = create_app(database)
    accounts = AccountRepository(database)
    headers = {"X-CSRF-Token": "test-token"}
    base = "/api/transport-requests"

    def signed_in_client(username, role, facility=None):
        accounts.create(username, "unused", role, facility)
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(username=username, csrf_token="test-token")
        return client

    dispatcher = signed_in_client("Sam", "dispatcher")
    courier = signed_in_client("Alex", "courier")
    other_courier = signed_in_client("Lee", "courier")
    laboratory = signed_in_client("Maya", "laboratory", "central lab")
    other_lab = signed_in_client("Drew", "laboratory", "West Lab")
    assert courier.get("/").location == "/courier"
    assert courier.get("/laboratory").location == "/"
    assert b"Laboratory intake" in laboratory.get("/laboratory").data
    assert laboratory.post(base, json={}, headers=headers).status_code == 403

    created = dispatcher.post(base, json={
        "sample_code": "LAB-001",
        "sample_type": "serum",
        "origin": "Clinic",
        "destination": "Central Lab",
    }, headers=headers)
    assert created.status_code == 201
    assert created.json["sample_type"] == "serum"
    request_url = base + "/" + created.json["id"]
    status_url = request_url + "/status"
    receipt_url = request_url + "/receipt"
    assert courier.get(request_url).status_code == 404
    assert other_lab.get(request_url + "/history").status_code == 404

    assert dispatcher.post(
        request_url + "/assign", json={"courier_name": "Drew"}, headers=headers,
    ).status_code == 400
    assigned = dispatcher.post(request_url + "/assign", json={"courier_name": "alex"}, headers=headers)
    assert assigned.status_code == 200
    assert courier.get(base).json["requests"][0]["courier_name"] == "Alex"
    assert other_courier.get(base).json == {"requests": []}
    assert other_courier.patch(status_url, json={"status": "picked_up"}, headers=headers).status_code == 404
    assert laboratory.patch(status_url, json={"status": "picked_up"}, headers=headers).status_code == 403
    assert laboratory.post(receipt_url, json={"condition": "accepted"}, headers=headers).status_code == 409
    assert laboratory.get(base).json["requests"][0]["status"] == "assigned"
    assert other_lab.get(base).json == {"requests": []}

    for status in ("picked_up", "delivered"):
        response = courier.patch(status_url, json={"status": status}, headers=headers)
        assert response.status_code == 200
    assert laboratory.post(receipt_url, json={"condition": "issue"}, headers=headers).status_code == 400
    received = laboratory.post(receipt_url, json={
        "condition": "issue", "note": "Label partly unreadable.", "actor": "Forged",
    }, headers=headers)
    assert received.status_code == 200
    assert laboratory.get(request_url).json["receipt_condition"] == "issue"
    assert laboratory.post(receipt_url, json={"condition": "accepted"}, headers=headers).status_code == 409

    details = dispatcher.get(request_url + "/history").json
    assert [(event["status"], event["actor"]) for event in details["history"]] == [
        ("assigned", "Sam"), ("picked_up", "Alex"), ("delivered", "Alex"), ("received", "Maya"),
    ]
    assert details["incidents"][0]["description"] == "Label partly unreadable."
    assert dispatcher.get(base).json["requests"][0]["open_incidents"] == 1


def test_transport_planning_changes_and_handoff(tmp_path):
    database = tmp_path / "transports.sqlite3"
    app = create_app(database)
    accounts = AccountRepository(database)
    headers = {"X-CSRF-Token": "test-token"}
    base = "/api/transport-requests"

    def sign_in(username, role):
        accounts.create(username, "unused", role, None)
        client = app.test_client()
        with client.session_transaction() as session:
            session.update(username=username, csrf_token="test-token")
        return client

    dispatcher = sign_in("Sam", "dispatcher")
    first = sign_in("Alex", "courier")
    second = sign_in("Lee", "courier")
    plan = {
        "sample_code": "RUN-001", "origin": "Clinic", "destination": "Lab",
        "container_count": 3, "pickup_at": "2030-01-01T12:00:00+04:00",
        "due_at": "2030-01-01T14:00:00+04:00", "pickup_contact": "East desk",
        "delivery_contact": "Receiving", "instructions": "Meet at the east entrance.",
    }
    invalid = dispatcher.post(base, json={**plan, "due_at": "2030-01-01T07:00:00Z"}, headers=headers)
    assert invalid.status_code == 400
    job = dispatcher.post(base, json=plan, headers=headers).json
    assert job["container_count"] == 3
    assert job["pickup_at"] == "2030-01-01T08:00:00+00:00"
    url = f"{base}/{job['id']}"

    for name in ("Alex", "Lee"):
        assert dispatcher.post(url + "/assign", json={"courier_name": name}, headers=headers).status_code == 200
    assert first.get(url).status_code == 404
    snapshot = second.get(url).json
    revised = {**plan, "revision": snapshot["revision"], "instructions": "Use the side entrance."}
    assert dispatcher.patch(url, json=revised, headers=headers).status_code == 200
    assert dispatcher.patch(url, json=revised, headers=headers).status_code == 409
    assert second.get(url).json["instructions"] == "Use the side entrance."

    pickup = {"status": "picked_up", "note": "Collected at the side entrance."}
    assert second.patch(url + "/status", json={**pickup, "revision": snapshot["revision"]}, headers=headers).status_code == 409
    assert second.patch(url + "/status", json=pickup, headers=headers).status_code == 200
    assert dispatcher.post(url + "/cancel", json={"reason": "Duplicate"}, headers=headers).status_code == 409
    assert dispatcher.post(url + "/assign", json={"courier_name": "Alex"}, headers=headers).status_code == 409
    assert second.get(url + "/history").json["history"][-1]["note"] == pickup["note"]

    another = dispatcher.post(base, json={**plan, "sample_code": "RUN-002"}, headers=headers).json
    another_url = f"{base}/{another['id']}"
    assert dispatcher.post(another_url + "/cancel", json={"reason": " "}, headers=headers).status_code == 400
    assert dispatcher.post(another_url + "/cancel", json={"reason": "Duplicate"}, headers=headers).json["status"] == "cancelled"
    events = dispatcher.get(another_url + "/history").json["history"]
    assert events[-1]["note"] == "Cancelled: Duplicate"
