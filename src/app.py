from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request

from .repository import TransportRequestRepository


def create_app(database_path=None):
    app = Flask(__name__)
    if database_path is None:
        database_path = Path(app.instance_path) / "transport.sqlite3"
    repository = TransportRequestRepository(database_path)

    next_status = {
        "pending": "assigned",
        "assigned": "picked_up",
        "picked_up": "delivered",
        "delivered": "received",
    }

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/transport-requests")
    def list_transport_requests():
        return jsonify(requests=repository.list_all())

    @app.post("/api/transport-requests")
    def create_transport_request():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        details = {}
        for field in ("sample_code", "origin", "destination"):
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                return jsonify(error=f"{field} is required."), 400
            details[field] = value.strip()

        if details["origin"].casefold() == details["destination"].casefold():
            return jsonify(error="Origin and destination must differ."), 400

        transport_request = {
            "id": str(uuid4()),
            **details,
            "status": "pending",
        }
        repository.save(transport_request)
        return jsonify(transport_request), 201

    def apply_status_change(request_id, status, actor, *, courier_name=None):
        current = repository.get(request_id)
        if current is None:
            return jsonify(error="Transport request not found."), 404

        if next_status.get(current["status"]) != status:
            return jsonify(error="Invalid status transition."), 409

        if status == "assigned" and not courier_name:
            return jsonify(error="Use the assign endpoint to assign a courier."), 400

        updated = repository.change_status(
            request_id,
            current["status"],
            status,
            actor,
            courier_name=courier_name,
        )
        if updated is None:
            return jsonify(error="Status changed. Reload the request and retry."), 409

        return jsonify(updated)

    @app.post("/api/transport-requests/<request_id>/assign")
    def assign_courier(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        courier_name = data.get("courier_name")
        actor = data.get("actor")
        if not isinstance(courier_name, str) or not courier_name.strip():
            return jsonify(error="courier_name is required."), 400
        if not isinstance(actor, str) or not actor.strip():
            return jsonify(error="actor is required."), 400

        return apply_status_change(
            request_id,
            "assigned",
            actor.strip(),
            courier_name=courier_name.strip(),
        )

    @app.patch("/api/transport-requests/<request_id>/status")
    def change_transport_status(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        status = data.get("status")
        actor = data.get("actor")
        if not isinstance(status, str) or not status.strip():
            return jsonify(error="status is required."), 400
        if not isinstance(actor, str) or not actor.strip():
            return jsonify(error="actor is required."), 400

        return apply_status_change(request_id, status, actor.strip())

    @app.get("/api/transport-requests/<request_id>/history")
    def get_transport_history(request_id):
        if repository.get(request_id) is None:
            return jsonify(error="Transport request not found."), 404

        return jsonify(history=repository.history(request_id))

    @app.get("/api/transport-requests/<request_id>")
    def get_transport_request(request_id):
        transport_request = repository.get(request_id)
        if transport_request is None:
            return jsonify(error="Transport request not found."), 404

        return jsonify(transport_request)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/courier")
    def courier_dashboard():
        return render_template("courier.html")

    return app


app = create_app()
