import sqlite3
from contextlib import closing
from pathlib import Path


class TransportRequestRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS transport_requests (
                    id TEXT PRIMARY KEY,
                    sample_code TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL,
                    courier_name TEXT
                )
            """)

            columns = connection.execute(
                "PRAGMA table_info(transport_requests)"
            ).fetchall()
            existing_columns = {column[1] for column in columns}
            for name, definition in (
                ("courier_name", "TEXT"),
                ("priority", "TEXT NOT NULL DEFAULT 'standard'"),
                ("due_at", "TEXT"),
                ("created_at", "TEXT"),
            ):
                if name not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE transport_requests ADD COLUMN {name} {definition}"
                    )

            connection.execute("""
                CREATE TABLE IF NOT EXISTS transport_history (
                    id INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    previous_status TEXT NOT NULL,
                    status TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS transport_incidents (
                    id INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL REFERENCES transport_requests(id),
                    description TEXT NOT NULL,
                    reported_by TEXT NOT NULL,
                    reported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    resolved_by TEXT,
                    resolved_at TEXT
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS transport_incidents_by_request
                ON transport_incidents (request_id, resolved_at)
            """)

    @staticmethod
    def _request_from_row(row):
        result = dict(row)
        if result["courier_name"] is None:
            del result["courier_name"]
        return result

    def save(self, transport_request):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("""
                INSERT INTO transport_requests
                    (id, sample_code, origin, destination, status, priority, due_at, created_at)
                VALUES
                    (:id, :sample_code, :origin, :destination, :status, :priority, :due_at, :created_at)
            """, transport_request)

    def get(self, request_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM transport_requests WHERE id = ?", (request_id,)
            ).fetchone()

        return self._request_from_row(row) if row is not None else None

    def list_all(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT request.*, (
                    SELECT COUNT(*) FROM transport_incidents AS incident
                    WHERE incident.request_id = request.id AND incident.resolved_at IS NULL
                ) AS open_incidents
                FROM transport_requests AS request
                ORDER BY request.rowid DESC
                """
            ).fetchall()

        return [self._request_from_row(row) for row in rows]

    def change_status(self, request_id, previous_status, status, actor, *, courier_name=None):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            result = connection.execute("""
                UPDATE transport_requests
                SET status = ?, courier_name = COALESCE(?, courier_name)
                WHERE id = ? AND status = ?
            """, (status, courier_name, request_id, previous_status))

            if result.rowcount != 1:
                return None

            connection.execute("""
                INSERT INTO transport_history (request_id, previous_status, status, actor)
                VALUES (?, ?, ?, ?)
            """, (request_id, previous_status, status, actor))

            row = connection.execute(
                "SELECT * FROM transport_requests WHERE id = ?", (request_id,)
            ).fetchone()

        return self._request_from_row(row)

    def history(self, request_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""
                SELECT previous_status, status, actor, changed_at
                FROM transport_history
                WHERE request_id = ?
                ORDER BY id
            """, (request_id,)).fetchall()

        return [dict(row) for row in rows]

    def incidents(self, request_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""
                SELECT id, description, reported_by, reported_at, resolved_by, resolved_at
                FROM transport_incidents
                WHERE request_id = ? ORDER BY id DESC
            """, (request_id,)).fetchall()
        return [dict(row) for row in rows]

    def report_incident(self, request_id, description, actor):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            result = connection.execute("""
                INSERT INTO transport_incidents (request_id, description, reported_by)
                VALUES (?, ?, ?)
            """, (request_id, description, actor))
            return result.lastrowid

    def resolve_incident(self, request_id, incident_id, actor):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            result = connection.execute("""
                UPDATE transport_incidents
                SET resolved_by = ?, resolved_at = CURRENT_TIMESTAMP
                WHERE request_id = ? AND id = ? AND resolved_at IS NULL
            """, (actor, request_id, incident_id))
            return result.rowcount == 1
