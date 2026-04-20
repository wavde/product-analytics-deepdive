"""Run case 03: north-star metric queries against the shared DuckDB."""

from __future__ import annotations

from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
SQL_DIR = HERE.parent / "sql"
DB_PATH = HERE.parent.parent / "01-funnel-and-retention" / "data" / "ecommerce.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}.")
        print("Run case-studies/01-funnel-and-retention/src/generate_data.py first.")
        raise SystemExit(1)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            print(f"\n=== {sql_file.name} ===")
            df = con.execute(sql_file.read_text()).fetch_df()
            if sql_file.name.startswith("01_north_star_daily"):
                print(df.tail(14).to_string(index=False))
            else:
                print(df.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
