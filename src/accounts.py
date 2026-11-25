import sqlite3
from contextlib import closing
from secrets import token_hex


class AccountRepository:
    def __init__(self, database_path):
        self.database_path = database_path
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    username TEXT COLLATE NOCASE PRIMARY KEY NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT,
                    facility TEXT
                )
            """)
            columns = {column[1] for column in connection.execute("PRAGMA table_info(accounts)")}
            if "role" not in columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN role TEXT")
            if "facility" not in columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN facility TEXT")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS application_settings (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    def session_secret(self):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "INSERT OR IGNORE INTO application_settings VALUES (?, ?)",
                ("session_secret", token_hex(32)),
            )
            return connection.execute(
                "SELECT value FROM application_settings WHERE name = ?", ("session_secret",)
            ).fetchone()[0]

    def create(self, username, password_hash, role, facility):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            result = connection.execute(
                "INSERT OR IGNORE INTO accounts (username, password_hash, role, facility) VALUES (?, ?, ?, ?)",
                (username, password_hash, role, facility),
            )
            return result.rowcount == 1

    def find(self, username):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT username, password_hash, role, facility FROM accounts WHERE username = ?", (username,)
            ).fetchone()
        return dict(row) if row is not None else None

    def set_initial_role(self, username, role, facility):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                "UPDATE accounts SET role = ?, facility = ? WHERE username = ? AND role IS NULL",
                (role, facility, username),
            )

    def directory(self):
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""
                SELECT username, role, facility FROM accounts
                WHERE role IN ('courier', 'laboratory') ORDER BY username
            """).fetchall()
        facilities = {row["facility"].casefold(): row["facility"] for row in rows if row["facility"]}
        return {
            "couriers": [row["username"] for row in rows if row["role"] == "courier"],
            "laboratories": sorted(facilities.values(), key=str.casefold),
        }
