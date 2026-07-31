from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_hash TEXT PRIMARY KEY,
                    processed_at TEXT NOT NULL,
                    task_id TEXT
                );
                CREATE TABLE IF NOT EXISTS scan_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    fetched INTEGER NOT NULL DEFAULT 0,
                    candidates INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )
            connection.commit()

    def is_processed(self, message_hash: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM processed_messages WHERE message_hash = ?",
                (message_hash,),
            ).fetchone()
        return row is not None

    def mark_processed(self, message_hash: str, task_id: str | None) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO processed_messages
                    (message_hash, processed_at, task_id)
                VALUES (?, ?, ?)
                """,
                (message_hash, datetime.now().astimezone().isoformat(), task_id),
            )
            connection.commit()

    def begin_scan(self) -> int:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "INSERT INTO scan_runs (started_at) VALUES (?)",
                (datetime.now().astimezone().isoformat(),),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def finish_scan(
        self,
        run_id: int,
        *,
        fetched: int,
        candidates: int,
        error: str | None = None,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                UPDATE scan_runs
                SET finished_at = ?, fetched = ?, candidates = ?, error = ?
                WHERE id = ?
                """,
                (
                    datetime.now().astimezone().isoformat(),
                    fetched,
                    candidates,
                    error,
                    run_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES ('last_scan_at', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (datetime.now().astimezone().isoformat(),),
            )
            if error:
                connection.execute(
                    """
                    INSERT INTO metadata (key, value) VALUES ('last_error', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (error,),
                )
            else:
                connection.execute("DELETE FROM metadata WHERE key = 'last_error'")
            connection.commit()

    def health(self) -> dict[str, str | None]:
        with closing(self._connect()) as connection:
            rows = connection.execute("SELECT key, value FROM metadata").fetchall()
        metadata = {str(row["key"]): str(row["value"]) for row in rows}
        return {
            "last_scan_at": metadata.get("last_scan_at"),
            "last_error": metadata.get("last_error"),
        }
