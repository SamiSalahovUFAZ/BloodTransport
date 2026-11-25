# BloodTransport

BloodTransport is a Flask and SQLite application for demonstrating the handoff of a sample between a dispatcher, a courier, and a receiving laboratory.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m flask --app src.app run --port 5001
```

Open [http://127.0.0.1:5001/](http://127.0.0.1:5001/) and choose **Create an account**. The SQLite database is created in the Flask instance directory.

## Demo

1. In **Dispatcher**, create a sample request to `Central Lab` and assign a courier named `Alex`.
2. In **Courier**, filter by `Alex` and mark the sample as picked up, then delivered.
3. In **Laboratory**, filter by `Central Lab` and confirm receipt. The signed-in username is recorded with every status change.

The dispatcher dashboard includes a summary of transport activity, search and filters, optional delivery deadlines, and CSV export of the current view. Open a request's details to see status changes, report an issue, or resolve a reported issue.

All signed-in users share the demo workspace. Courier and laboratory filters help users find assignments. The application does not implement per-role access control.

## Tests

```bash
.venv/bin/python -m pip install pytest
.venv/bin/python -m pytest -q
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_PATH` | Override the persistent SQLite file location. |
| `SECRET_KEY` | Set a session signing key. The app creates and persists a local fallback when this variable is unset. |
| `SESSION_COOKIE_SECURE` | Set to `1` when serving the app over HTTPS. |
