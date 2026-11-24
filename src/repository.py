import sqlite3
from contextlib import closing
from pathlib import Path


class TransportRequestRepository:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS transport_requests (
                    id TEXT PRIMARY KEY,
                    sample_code TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    status TEXT NOT NULL
                )
            """)

            connection.execute(
                "CREATE TABLE IF NOT EXISTS transport_history ("
                "id INTEGER PRIMARY KEY, request_id TEXT NOT NULL, "
                "previous_status TEXT NOT NULL, status TEXT NOT NULL, "
                "actor TEXT NOT NULL, changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )

    def save(self, transport_request):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute("""
                INSERT INTO transport_requests (id, sample_code, origin, destination, status)
                VALUES (:id, :sample_code, :origin, :destination, :status)
            """, transport_request)

    def get(self, request_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM transport_requests WHERE id = ?", (request_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list_all(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM transport_requests ORDER BY rowid DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def change_status(self, request_id, previous_status, status, actor):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            result = connection.execute(
                "UPDATE transport_requests SET status = ? WHERE id = ? AND status = ?",
                (status, request_id, previous_status),
            )
            if result.rowcount != 1:
                return None

            connection.execute(
                "INSERT INTO transport_history (request_id, previous_status, status, actor) "
                "VALUES (?, ?, ?, ?)",
                (request_id, previous_status, status, actor),
            )
            row = connection.execute(
                "SELECT * FROM transport_requests WHERE id = ?", (request_id,)
            ).fetchone()
        return dict(row)

    def history(self, request_id):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT previous_status, status, actor, changed_at "
                "FROM transport_history WHERE request_id = ? ORDER BY id",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]
