from datetime import datetime, timezone
from os import environ
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, session

from .accounts import AccountRepository
from .auth import add_auth
from .repository import TransportRequestRepository


def create_app(database_path=None):
    app = Flask(__name__)
    if database_path is None:
        database_path = environ.get("DATABASE_PATH") or Path(app.instance_path) / "transport.sqlite3"
    repository = TransportRequestRepository(database_path)
    accounts = AccountRepository(database_path)
    app.secret_key = environ.get("SECRET_KEY") or accounts.session_secret()
    app.config.update(
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=environ.get("SESSION_COOKIE_SECURE") == "1",
    )
    add_auth(app, accounts)

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
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
                return jsonify(error=f"{field} must contain 1–100 characters."), 400
            details[field] = value.strip()

        if details["origin"].casefold() == details["destination"].casefold():
            return jsonify(error="Origin and destination must differ."), 400

        priority = data.get("priority", "standard")
        if priority not in ("standard", "urgent", "critical"):
            return jsonify(error="Choose a valid priority."), 400

        due_at = data.get("due_at")
        if due_at is not None:
            if not isinstance(due_at, str):
                return jsonify(error="Delivery deadline must include a time zone."), 400
            try:
                deadline = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                if deadline.utcoffset() is None:
                    raise ValueError("No time zone")
                due_at = deadline.astimezone(timezone.utc).isoformat(timespec="seconds")
            except (ValueError, OverflowError):
                return jsonify(error="Delivery deadline must include a valid time and time zone."), 400

        transport_request = {
            "id": str(uuid4()),
            **details,
            "status": "pending",
            "priority": priority,
            "due_at": due_at,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        repository.save(transport_request)
        return jsonify(transport_request), 201

    def apply_status_change(request_id, status, *, courier_name=None):
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
            session["username"],
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
        if not isinstance(courier_name, str) or not courier_name.strip():
            return jsonify(error="courier_name is required."), 400

        return apply_status_change(
            request_id,
            "assigned",
            courier_name=courier_name.strip(),
        )

    @app.patch("/api/transport-requests/<request_id>/status")
    def change_transport_status(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        status = data.get("status")
        if not isinstance(status, str) or not status.strip():
            return jsonify(error="status is required."), 400

        return apply_status_change(request_id, status.strip())

    @app.get("/api/transport-requests/<request_id>/history")
    def get_transport_history(request_id):
        if repository.get(request_id) is None:
            return jsonify(error="Transport request not found."), 404

        return jsonify(history=repository.history(request_id), incidents=repository.incidents(request_id))

    @app.post("/api/transport-requests/<request_id>/incidents")
    def report_transport_incident(request_id):
        data = request.get_json(silent=True)
        description = data.get("description") if isinstance(data, dict) else None
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 500:
            return jsonify(error="Describe the issue in 1–500 characters."), 400
        if repository.get(request_id) is None:
            return jsonify(error="Transport request not found."), 404
        incident_id = repository.report_incident(request_id, description.strip(), session["username"])
        return jsonify(id=incident_id), 201

    @app.patch("/api/transport-requests/<request_id>/incidents/<int:incident_id>/resolve")
    def resolve_transport_incident(request_id, incident_id):
        if not repository.resolve_incident(request_id, incident_id, session["username"]):
            return jsonify(error="Issue is already resolved or could not be found."), 409
        return jsonify(resolved=True)

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

    @app.get("/laboratory")
    def laboratory_dashboard():
        return render_template("laboratory.html")

    return app


app = create_app()
