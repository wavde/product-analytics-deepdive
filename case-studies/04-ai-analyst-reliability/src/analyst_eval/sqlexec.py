"""Sandboxed SQL execution and deterministic result formatting."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

import duckdb

DISPLAY_ROWS = 50
MAX_ROWS = 10_000
DISPLAY_CHARS = 4_000


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None

    def scalar(self) -> float | None:
        if not self.ok or not self.rows or not self.rows[0]:
            return None
        return to_number(self.rows[0][0])


def to_number(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def execute(con: duckdb.DuckDBPyConnection, sql: str, timeout: float = 30.0) -> QueryResult:
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        cur = con.execute(sql)
        if cur.description is None:
            return QueryResult()
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        return QueryResult(cols, rows[:MAX_ROWS], truncated=len(rows) > MAX_ROWS)
    except duckdb.InterruptException:
        return QueryResult(error=f"Query cancelled after {timeout:.0f}s timeout.")
    except duckdb.Error as err:
        return QueryResult(error=f"{type(err).__name__}: {str(err)[:500]}")
    finally:
        timer.cancel()


def _cell(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def format_result(res: QueryResult) -> str:
    if not res.ok:
        return f"ERROR {res.error}"
    if not res.columns:
        return "OK (no result set)"
    lines = [" | ".join(res.columns)]
    for row in res.rows[:DISPLAY_ROWS]:
        lines.append(" | ".join(_cell(v) for v in row))
    shown = min(len(res.rows), DISPLAY_ROWS)
    more = "+" if res.truncated else ""
    lines.append(f"({len(res.rows)}{more} rows, showing {shown})")
    text = "\n".join(lines)
    if len(text) > DISPLAY_CHARS:
        text = text[:DISPLAY_CHARS] + "\n... (output truncated)"
    return text
