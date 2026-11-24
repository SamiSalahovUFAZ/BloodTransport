from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request


from .repository import TransportRequestRepository


def create_app(database_path=None):
    app = Flask(__name__)
    if database_path is None:
        database_path = Path(app.instance_path) / "transport.sqlite3"
    repository = TransportRequestRepository(database_path)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    @app.post("/api/transport-requests")
    def create_transport_request():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Provide a JSON object."), 400

        required_fields = ("sample_code", "origin", "destination")
        details = {}

        for field in required_fields:
            value = data.get(field)
            if not isinstance(value, str) or not value.strip():
                return jsonify(error=f"{field} is required."), 400
            details[field] = value.strip()

        if details["origin"].casefold() == details["destination"].casefold():
            return jsonify(error="Origin and destination must differ."), 400

        request_id = str(uuid4())
        transport_request = {
            "id": request_id,
            **details,
            "status": "pending",
        }
        repository.save(transport_request)
        return jsonify(transport_request), 201

    @app.get("/api/transport-requests/<request_id>")
    def get_transport_request(request_id):
        transport_request = repository.get(request_id)
        if transport_request is None:
            return jsonify(error="Transport request not found."), 404
        return jsonify(transport_request)

    @app.get("/")
    def index():
        return render_template("index.html")

    return app


app = create_app()
