from uuid import uuid4

from flask import Flask, jsonify, request


def create_app():
    app = Flask(__name__)
    transport_requests = {}

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
        transport_requests[request_id] = transport_request
        return jsonify(transport_request), 201

    @app.get("/api/transport-requests/<request_id>")
    def get_transport_request(request_id):
        transport_request = transport_requests.get(request_id)
        if transport_request is None:
            return jsonify(error="Transport request not found."), 404
        return jsonify(transport_request)

    return app


app = create_app()
