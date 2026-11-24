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
