from functools import wraps

from flask import g, jsonify


ROLE_LABELS = {
    "dispatcher": "Dispatcher",
    "courier": "Courier",
    "laboratory": "Laboratory",
}

SAMPLE_TYPES = {
    "blood": "Blood",
    "serum": "Serum",
    "plasma": "Plasma",
    "urine": "Urine",
    "swab": "Swab",
    "other": "Other",
    "unspecified": "Unspecified",
}


def role_required(role):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.account["role"] != role:
                return jsonify(error="Your role cannot perform this action."), 403
            return view(*args, **kwargs)

        return wrapped

    return decorate


def can_view(account, job):
    role = account["role"]
    if role == "dispatcher":
        return True
    if role == "courier":
        return (job.get("courier_name") or "").casefold() == account["username"].casefold()
    return role == "laboratory" and bool(account["facility"]) and job["destination"].casefold() == account["facility"].casefold()
