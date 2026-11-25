import sqlite3
from contextlib import closing
from secrets import token_hex


class AccountRepository:
    def __init__(self, database_path):
        self.database_path = database_path
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    username TEXT COLLATE NOCASE PRIMARY KEY NOT NULL,
                    password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS application_settings (
                    name TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
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

    def create(self, username, password_hash):
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            result = connection.execute(
                "INSERT OR IGNORE INTO accounts (username, password_hash) VALUES (?, ?)",
                (username, password_hash),
            )
            return result.rowcount == 1

    def find(self, username):
        with closing(sqlite3.connect(self.database_path)) as connection:
            return connection.execute(
                "SELECT username, password_hash FROM accounts WHERE username = ?", (username,)
            ).fetchone()
