from src.app import create_app


def test_laboratory_receipt_workflow(tmp_path):
    client = create_app(tmp_path / "transports.sqlite3").test_client()
    dashboard = client.get("/laboratory")
    assert dashboard.status_code == 200
    assert b"Laboratory dashboard" in dashboard.data

    created = client.post("/api/transport-requests", json={
        "sample_code": "LAB-001",
        "origin": "Clinic",
        "destination": "Central Lab",
    })
    assert created.status_code == 201
    request_url = "/api/transport-requests/" + created.json["id"]
    status_url = request_url + "/status"

    assigned = client.post(request_url + "/assign", json={
        "courier_name": "Alex",
        "actor": "Dispatcher",
    })
    assert assigned.status_code == 200

    early_receipt = client.patch(status_url, json={"status": "received", "actor": "Maya"})
    assert early_receipt.status_code == 409

    for status in ("picked_up", "delivered"):
        response = client.patch(status_url, json={"status": status, "actor": "Alex"})
        assert response.status_code == 200

    received = client.patch(status_url, json={"status": "received", "actor": "Maya"})
    assert received.status_code == 200
    assert client.get(request_url).json["status"] == "received"

    history = client.get(request_url + "/history").json["history"]
    assert [(event["status"], event["actor"]) for event in history] == [
        ("assigned", "Dispatcher"),
        ("picked_up", "Alex"),
        ("delivered", "Alex"),
        ("received", "Maya"),
    ]
