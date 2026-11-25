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

1. Register three demo accounts with the **Dispatcher**, **Courier**, and **Laboratory** roles. Use `Alex` for the courier username and `Central Lab` for the laboratory location.
2. Sign in as the dispatcher, create a typed sample request to `Central Lab`, and assign `Alex`.
3. Sign in as Alex to see the assigned run, record pickup and delivery, and report any delays.
4. Sign in with the laboratory account to filter the sample queue by type or stage and record the intake outcome. Choosing **Received with issue** requires a note and opens an issue for the dispatcher.

The dispatcher dashboard includes a summary of transport activity, search and filters, optional delivery deadlines, and CSV export of the current view. Open a request's details to see status changes, report an issue, or resolve a reported issue.

The request form also records container count, scheduled pickup, pickup and delivery contacts, and handoff instructions. Dispatchers can edit, reassign, or cancel a request before pickup. Cancellation requires a reason. Couriers can add a note when recording pickup or delivery, and all three teams can review the handoff history for requests they can access.

Each signed-in account opens its own workspace. The API enforces the role and limits courier and laboratory records to their assignments and registered destinations. Existing accounts choose their role once at sign-in. Registration is self-service for the classroom demo, so role and laboratory ownership are not verified.

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
