import re
from hmac import compare_digest
from secrets import token_urlsafe

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


USERNAME = re.compile(r"[A-Za-z0-9_.-]{3,32}")
PUBLIC_ENDPOINTS = {"health", "static", "auth.login", "auth.register"}
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = token_urlsafe(32)
    return session["csrf_token"]


def add_auth(app, accounts):
    auth = Blueprint("auth", __name__)
    missing_account_hash = generate_password_hash(token_urlsafe(32))
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def require_session():
        if request.endpoint is None:
            return None
        is_api = request.path.startswith("/api/")
        if request.endpoint not in PUBLIC_ENDPOINTS and "username" not in session:
            if is_api:
                return jsonify(error="Sign in to continue."), 401
            return redirect(url_for("auth.login"))

        if request.method not in READ_METHODS:
            submitted = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
            expected = session.get("csrf_token")
            if not expected or not submitted.isascii() or not compare_digest(expected, submitted):
                if is_api:
                    return jsonify(error="Refresh the page and try again."), 400
                return render_template(
                    "auth.html",
                    registering=request.endpoint == "auth.register",
                    error="This form has expired. Please try again.",
                ), 400

    @app.after_request
    def prevent_private_caching(response):
        if request.endpoint not in {"static", "health"}:
            response.headers["Cache-Control"] = "no-store"
        return response

    def sign_in(username):
        session.clear()
        session["username"] = username
        return redirect(url_for("index"), code=303)

    @auth.route("/login", methods=["GET", "POST"])
    def login():
        if "username" in session:
            return redirect(url_for("index"))
        if request.method == "GET":
            return render_template("auth.html", registering=False)

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        account = accounts.find(username) if USERNAME.fullmatch(username) else None
        stored_hash = account[1] if account is not None else missing_account_hash
        valid = 0 < len(password) <= 128 and check_password_hash(stored_hash, password)
        if account is not None and valid:
            return sign_in(account[0])
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
        if not USERNAME.fullmatch(username):
            error = "Use 3–32 letters, numbers, dots, hyphens or underscores for your username."
        elif not 10 <= len(password) <= 128:
            error = "Choose a password with 10–128 characters."
        elif password != request.form.get("confirm_password"):
            error = "The passwords do not match."
        elif accounts.create(username, generate_password_hash(password)):
            return sign_in(username)
        else:
            error = "That username is already in use."
        return render_template(
            "auth.html", registering=True, username=username[:32], error=error,
        ), 400

    @auth.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth.login"), code=303)

    app.register_blueprint(auth)
