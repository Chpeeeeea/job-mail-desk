from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from collections.abc import Iterable


class StateVersionMismatch(RuntimeError):
    """Raised when a state file belongs to another processing build."""


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

    def bootstrap_processed_from(
        self,
        sources: Iterable[Path],
        *,
        parser_version: str,
    ) -> int:
        """Copy only deduplication markers from the newest compatible state DB."""
        with closing(self._connect()) as connection:
            existing = connection.execute(
                "SELECT COUNT(*) AS count FROM processed_messages"
            ).fetchone()
            if existing and int(existing["count"]):
                return 0

        for source in sources:
            if source == self.path or not source.exists():
                continue
            try:
                with closing(sqlite3.connect(source)) as source_connection:
                    source_connection.row_factory = sqlite3.Row
                    metadata = source_connection.execute(
                        "SELECT value FROM metadata WHERE key = 'parser_version'"
                    ).fetchone()
                    if not metadata or str(metadata["value"]) != parser_version:
                        continue
                    rows = source_connection.execute(
                        """
                        SELECT message_hash, processed_at, task_id
                        FROM processed_messages
                        """
                    ).fetchall()
            except sqlite3.Error:
                continue
            if not rows:
                continue
            with closing(self._connect()) as connection:
                connection.executemany(
                    """
                    INSERT OR IGNORE INTO processed_messages
                        (message_hash, processed_at, task_id)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (row["message_hash"], row["processed_at"], row["task_id"])
                        for row in rows
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO metadata (key, value) VALUES ('dedup_bootstrap_source', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (source.name,),
                )
                connection.commit()
            return len(rows)
        return 0

    def has_successful_scan(self) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT 1 FROM scan_runs
                WHERE finished_at IS NOT NULL AND error IS NULL
                LIMIT 1
                """
            ).fetchone()
        return row is not None

    def prepare_parser_version(self, version: str) -> bool:
        """Record the processing version without destroying deduplication state."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'parser_version'"
            ).fetchone()
            current = str(row["value"]) if row else None
            if current and current != version:
                message = (
                    "state parser version mismatch: "
                    f"state={current}, runtime={version}; automatic scan stopped"
                )
                connection.execute(
                    """
                    INSERT INTO metadata (key, value) VALUES ('last_error', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (message,),
                )
                connection.commit()
                raise StateVersionMismatch(message)
            if current == version:
                return False
            connection.execute(
                """
                INSERT INTO metadata (key, value) VALUES ('parser_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (version,),
            )
            connection.commit()
            return True

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
            "state_parser_version": metadata.get("parser_version"),
        }
