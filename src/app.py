from datetime import datetime, timezone
from os import environ
from pathlib import Path
from uuid import uuid4

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

from .accounts import AccountRepository
from .auth import add_auth
from .repository import TransportRequestRepository
from .roles import SAMPLE_TYPES, can_view, role_required


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
    app.jinja_env.globals["sample_types"] = SAMPLE_TYPES

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
        return jsonify(requests=[job for job in repository.list_all() if can_view(g.account, job)])

    def visible_job(request_id):
        job = repository.get(request_id)
        return job if job is not None and can_view(g.account, job) else None

    @app.post("/api/transport-requests")
    @role_required("dispatcher")
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
        sample_type = data.get("sample_type", "unspecified")
        if not isinstance(sample_type, str) or sample_type not in SAMPLE_TYPES:
            return jsonify(error="Choose a valid sample type."), 400

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
            "sample_type": sample_type,
        }
        repository.save(transport_request)
        return jsonify(transport_request), 201

    def apply_status_change(request_id, status, **details):
        current = visible_job(request_id)
        if current is None:
            return jsonify(error="Transport request not found."), 404

        if next_status.get(current["status"]) != status:
            return jsonify(error="Invalid status transition."), 409

        updated = repository.change_status(
            request_id,
            current["status"],
            status,
            g.account["username"],
            **details,
        )
        if updated is None:
            return jsonify(error="Status changed. Reload the request and retry."), 409

        return jsonify(updated)

    @app.post("/api/transport-requests/<request_id>/assign")
    @role_required("dispatcher")
    def assign_courier(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        courier_name = data.get("courier_name")
        courier = accounts.find(courier_name.strip()) if isinstance(courier_name, str) else None
        if courier is None or courier["role"] != "courier":
            return jsonify(error="Select a registered courier."), 400

        return apply_status_change(
            request_id,
            "assigned",
            courier_name=courier["username"],
        )

    @app.patch("/api/transport-requests/<request_id>/status")
    @role_required("courier")
    def change_transport_status(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        status = data.get("status")
        if status not in ("picked_up", "delivered"):
            return jsonify(error="Couriers can record pickup or delivery."), 400

        return apply_status_change(request_id, status)

    @app.post("/api/transport-requests/<request_id>/receipt")
    @role_required("laboratory")
    def receive_transport_request(request_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400
        condition = data.get("condition")
        note = data.get("note", "")
        if condition not in ("accepted", "issue"):
            return jsonify(error="Choose a receipt outcome."), 400
        if not isinstance(note, str) or len(note.strip()) > 500 or (condition == "issue" and not note.strip()):
            return jsonify(error="Enter a receipt note of up to 500 characters. A note is required for issues."), 400
        return apply_status_change(
            request_id, "received", receipt_condition=condition, receipt_note=note.strip() or None,
        )

    @app.get("/api/transport-requests/<request_id>/history")
    def get_transport_history(request_id):
        if visible_job(request_id) is None:
            return jsonify(error="Transport request not found."), 404

        return jsonify(history=repository.history(request_id), incidents=repository.incidents(request_id))

    @app.post("/api/transport-requests/<request_id>/incidents")
    def report_transport_incident(request_id):
        data = request.get_json(silent=True)
        description = data.get("description") if isinstance(data, dict) else None
        if not isinstance(description, str) or not 1 <= len(description.strip()) <= 500:
            return jsonify(error="Describe the issue in 1–500 characters."), 400
        if visible_job(request_id) is None:
            return jsonify(error="Transport request not found."), 404
        incident_id = repository.report_incident(request_id, description.strip(), g.account["username"])
        return jsonify(id=incident_id), 201

    @app.patch("/api/transport-requests/<request_id>/incidents/<int:incident_id>/resolve")
    @role_required("dispatcher")
    def resolve_transport_incident(request_id, incident_id):
        if not repository.resolve_incident(request_id, incident_id, g.account["username"]):
            return jsonify(error="Issue is already resolved or could not be found."), 409
        return jsonify(resolved=True)

    @app.get("/api/transport-requests/<request_id>")
    def get_transport_request(request_id):
        transport_request = visible_job(request_id)
        if transport_request is None:
            return jsonify(error="Transport request not found."), 404

        return jsonify(transport_request)

    @app.get("/")
    def index():
        if g.account["role"] == "courier":
            return redirect(url_for("courier_dashboard"))
        if g.account["role"] == "laboratory":
            return redirect(url_for("laboratory_dashboard"))
        return render_template("index.html", directory=accounts.directory())

    @app.get("/courier")
    def courier_dashboard():
        if g.account["role"] != "courier":
            return redirect(url_for("index"))
        return render_template("courier.html")

    @app.get("/laboratory")
    def laboratory_dashboard():
        if g.account["role"] != "laboratory":
            return redirect(url_for("index"))
        return render_template("laboratory.html")

    return app


app = create_app()
