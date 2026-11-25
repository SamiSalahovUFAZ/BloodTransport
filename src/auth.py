import re
from hmac import compare_digest
from secrets import token_urlsafe

from flask import Blueprint, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .roles import ROLE_LABELS

USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,32}")
PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000000"
PUBLIC_ENDPOINTS = {"health", "static", "auth.login", "auth.register"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = token_urlsafe(32)
    return session["csrf_token"]


def add_auth(app, accounts):
    auth = Blueprint("auth", __name__)
    missing_account_hash = generate_password_hash(token_urlsafe(32), method=PASSWORD_HASH_METHOD)
    app.jinja_env.globals["csrf_token"] = csrf_token
    app.jinja_env.globals["role_labels"] = ROLE_LABELS

    @app.before_request
    def require_session():
        if request.endpoint is None:
            return None
        is_api = request.path.startswith("/api/")
        tracking_id = request.view_args.get("request_id") if request.endpoint == "workspace_tools.track" else None
        if request.endpoint not in {"static", "health"}:
            username = session.get("username")
            g.account = accounts.find(username) if username else None
            if username and g.account is None:
                session.clear()
            if request.endpoint not in PUBLIC_ENDPOINTS:
                if g.account is None:
                    if is_api:
                        return jsonify(error="Sign in to continue."), 401
                    if tracking_id and len(tracking_id) <= 36:
                        session["tracking_return"] = tracking_id
                    return redirect(url_for("auth.login"))
                if g.account["role"] is None and request.endpoint not in {"auth.setup_role", "auth.logout"}:
                    if is_api:
                        return jsonify(error="Choose a workspace role first."), 403
                    if tracking_id and len(tracking_id) <= 36:
                        session["tracking_return"] = tracking_id
                    return redirect(url_for("auth.setup_role"))

        if request.method not in READ_METHODS:
            submitted = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("csrf_token")
            if not expected or not submitted.isascii() or not compare_digest(expected, submitted):
                if is_api:
                    return jsonify(error="Refresh the page and try again."), 400
                return render_template(
                    "auth.html",
                    registering=request.endpoint == "auth.register",
                    setting_up=request.endpoint == "auth.setup_role",
                    error="This form has expired. Please try again.",
                ), 400

    @app.after_request
    def prevent_private_caching(response):
        if request.endpoint not in {"static", "health"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    def workspace_destination(tracking_return):
        if tracking_return:
            return redirect(url_for("workspace_tools.track", request_id=tracking_return), code=303)
        return redirect(url_for("index"), code=303)

    def sign_in(username):
        tracking_return = session.get("tracking_return")
        session.clear()
        session["username"] = username
        return workspace_destination(tracking_return)

    def role_selection():
        role = request.form.get("role", "")
        facility = request.form.get("facility", "").strip()
        if role not in ROLE_LABELS:
            return role, facility, "Select a workspace role."
        if role == "laboratory" and not 1 <= len(facility) <= 100:
            return role, facility, "Enter your laboratory location (1–100 characters)."
        return role, facility if role == "laboratory" else None, None

    @auth.route("/login", methods=["GET", "POST"])
    def login():
        if "username" in session:
            return redirect(url_for("index"))
        if request.method == "GET":
            return render_template("auth.html", registering=False)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        account = accounts.find(username) if USERNAME.fullmatch(username) else None
        stored_hash = account["password_hash"] if account is not None else missing_account_hash
        valid = 0 < len(password) <= 128 and check_password_hash(stored_hash, password)
        if account is not None and valid:
            return sign_in(account["username"])
        return render_template(
            "auth.html", registering=False, username=username[:32],
            error="That username or password did not match.",
        ), 401

    @auth.route("/register", methods=["GET", "POST"])
    def register():
        if "username" in session:
            return redirect(url_for("index"))
        if request.method == "GET":
            return render_template("auth.html", registering=True)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role, facility, role_error = role_selection()
        if not USERNAME.fullmatch(username):
            error = "Use 3–32 letters, numbers, dots, hyphens or underscores for your username."
        elif not 10 <= len(password) <= 128:
            error = "Choose a password with 10–128 characters."
        elif password != request.form.get("confirm_password"):
            error = "The passwords do not match."
        elif role_error:
            error = role_error
        elif accounts.create(username, generate_password_hash(password, method=PASSWORD_HASH_METHOD), role, facility):
            return sign_in(username)
        else:
            error = "That username is already in use."
        return render_template(
            "auth.html", registering=True, username=username[:32], role=role, facility=facility, error=error,
        ), 400

    @auth.route("/choose-role", methods=["GET", "POST"])
    def setup_role():
        if g.account["role"] is not None:
            return redirect(url_for("index"))
        if request.method == "GET":
            return render_template("auth.html", setting_up=True)
        role, facility, error = role_selection()
        if error:
            return render_template("auth.html", setting_up=True, role=role, facility=facility, error=error), 400
        accounts.set_initial_role(g.account["username"], role, facility)
        return workspace_destination(session.pop("tracking_return", None))

    @auth.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth.login"), code=303)

    app.register_blueprint(auth)
