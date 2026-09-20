"""Conexão com o banco e aplicação do schema.

SQLite na V1. O SQL é padrão o suficiente para migrar a PostgreSQL trocando
esta camada — nenhum módulo acima dela conhece o driver.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = "1"


def utcnow() -> str:
    """Timestamp ISO em UTC. Um único lugar gera 'agora' no projeto inteiro."""
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Wrapper fino sobre sqlite3 com o schema garantido."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.apply_schema()

    # ------------------------------------------------------------------ core
    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def apply_schema(self) -> None:
        self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SCHEMA_VERSION,),
        )

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, tuple(params))

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, [tuple(r) for r in rows])

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        return self._conn.execute(sql, tuple(params)).fetchone()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self._conn.execute("BEGIN")
        try:
            yield self._conn
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_database(path: Path | str | None = None) -> Database:
    if path is None:
        from irai.config import get_settings

        path = get_settings().database_path
    return Database(path)
