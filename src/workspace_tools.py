from io import BytesIO

import qrcode
from flask import Blueprint, Response, abort, current_app, g, render_template, request, url_for
from qrcode.image.svg import SvgPathImage

from .roles import can_view


STAGE_LABELS = {
    "pending": "Awaiting assignment",
    "assigned": "Awaiting pickup",
    "picked_up": "In transit",
    "delivered": "Delivered",
    "received": "Received",
    "cancelled": "Cancelled",
}


def register_workspace_tools(app, repository):
    tools = Blueprint("workspace_tools", __name__)
    app.jinja_env.globals["stage_labels"] = STAGE_LABELS

    def scoped_job(request_id):
        job = repository.get(request_id)
        if job is None or not can_view(g.account, job):
            abort(404)
        return job

    def scoped_jobs():
        return [job for job in repository.list_all() if can_view(g.account, job)]

    @tools.get("/tools")
    def hub():
        return render_template("tools/hub.html")

    @tools.get("/tools/planner")
    def planner():
        return render_template("tools/planner.html", jobs=scoped_jobs())

    @tools.get("/tools/incidents")
    def incidents():
        jobs = {job["id"]: job for job in scoped_jobs()}
        incident_rows = [issue for issue in repository.incident_feed() if issue["request_id"] in jobs]
        status = request.args.get("status", "open")
        if status not in {"open", "resolved", "all"}:
            abort(400)
        visible = [
            issue for issue in incident_rows
            if status == "all" or (issue["resolved_at"] is not None) == (status == "resolved")
        ]
        return render_template(
            "tools/incidents.html", incidents=visible, jobs=jobs, status=status,
            open_count=sum(issue["resolved_at"] is None for issue in incident_rows),
            total=len(incident_rows),
        )

    @tools.get("/tools/labels")
    def labels():
        query = request.args.get("q", "").strip().casefold()
        jobs = [job for job in scoped_jobs() if query in job["sample_code"].casefold()]
        return render_template("tools/labels.html", jobs=jobs, query=query)

    @tools.get("/tools/labels/<request_id>")
    def label(request_id):
        return render_template("tools/label.html", job=scoped_job(request_id))

    @tools.get("/tools/labels/<request_id>/qr.svg")
    def qr_code(request_id):
        scoped_job(request_id)
        scheme = "https" if current_app.config["SESSION_COOKIE_SECURE"] else request.scheme
        url = url_for("workspace_tools.track", request_id=request_id, _external=True, _scheme=scheme)
        image = qrcode.make(url, image_factory=SvgPathImage)
        output = BytesIO()
        image.save(output)
        return Response(output.getvalue(), mimetype="image/svg+xml")

    @tools.get("/tracking/<request_id>")
    def track(request_id):
        job = scoped_job(request_id)
        return render_template(
            "tools/track.html", job=job, events=repository.history(request_id),
            incidents=repository.incidents(request_id),
        )

    app.register_blueprint(tools)
