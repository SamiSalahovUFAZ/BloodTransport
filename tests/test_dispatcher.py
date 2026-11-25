import sqlite3
from contextlib import closing

from src.app import create_app
from src.accounts import AccountRepository


def test_dispatcher_planning_and_issue_tracking(tmp_path):
    database = tmp_path / "transports.sqlite3"
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.executescript("""
            CREATE TABLE transport_requests (
                id TEXT PRIMARY KEY, sample_code TEXT NOT NULL, origin TEXT NOT NULL,
                destination TEXT NOT NULL, status TEXT NOT NULL
            );
            INSERT INTO transport_requests VALUES ('legacy', 'OLD-01', 'Clinic', 'Lab', 'pending');
        """)

    client = create_app(database).test_client()
    AccountRepository(database).create("Dispatcher", "unused", "dispatcher", None)
    with client.session_transaction() as session:
        session.update(username="Dispatcher", csrf_token="test-token")
    headers = {"X-CSRF-Token": "test-token"}
    url = "/api/transport-requests"
    legacy = client.get(url).json["requests"][0]
    assert legacy["priority"] == "standard" and legacy["due_at"] is None

    details = {"sample_code": "NEW-01", "origin": "Clinic", "destination": "Lab"}
    response = client.post(url, json={**details, "due_at": "2035-02-14T09:00"}, headers=headers)
    assert response.status_code == 400
    response = client.post(url, json={
        **details, "priority": "urgent", "due_at": "2035-02-14T09:00:00+04:00",
    }, headers=headers)
    assert response.status_code == 201
    saved = response.json
    assert saved["priority"] == "urgent"
    assert saved["due_at"] == "2035-02-14T05:00:00+00:00"
    request_url = f"{url}/{saved['id']}"

    incident = client.post(
        request_url + "/incidents", json={"description": "Pickup address changed."}, headers=headers,
    )
    assert incident.status_code == 201
    assert client.get(url).json["requests"][0]["open_incidents"] == 1
    resolve_url = request_url + f"/incidents/{incident.json['id']}/resolve"
    assert client.patch(resolve_url, headers=headers).status_code == 200
    assert client.patch(resolve_url, headers=headers).status_code == 409
    logged = client.get(request_url + "/history").json["incidents"][0]
    assert logged["reported_by"] == logged["resolved_by"] == "Dispatcher"
    assert client.get(url).json["requests"][0]["open_incidents"] == 0
