"""Run all three funnel/retention queries against the DuckDB snapshot."""

from __future__ import annotations

from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
SQL_DIR = HERE.parent / "sql"
DB_PATH = HERE.parent / "data" / "ecommerce.db"


def run_query(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    print(f"\n=== {path.name} ===")
    sql = path.read_text()
    result = con.execute(sql).fetch_df()
    print(result.to_string(index=False))


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run src/generate_data.py first.")
        raise SystemExit(1)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            run_query(con, sql_file)
    finally:
        con.close()


if __name__ == "__main__":
    main()
