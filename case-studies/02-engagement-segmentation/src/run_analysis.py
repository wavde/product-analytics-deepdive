"""Run case 02: SQL queries + k-means segmentation."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
SQL_DIR = HERE.parent / "sql"
DB_PATH = HERE.parent.parent / "01-funnel-and-retention" / "data" / "ecommerce.db"

sys.path.insert(0, str(HERE))
from segment import cluster_summary, fit_kmeans, label_clusters, load_features  # noqa: E402


def main() -> None:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}.")
        print("Run case-studies/01-funnel-and-retention/src/generate_data.py first.")
        raise SystemExit(1)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for sql_file in sorted(SQL_DIR.glob("*.sql")):
            print(f"\n=== {sql_file.name} ===")
            print(con.execute(sql_file.read_text()).fetch_df().to_string(index=False))
    finally:
        con.close()

    print("\n=== K-means engagement segmentation (k=4) ===")
    features = load_features()
    labelled, _, _ = fit_kmeans(features, k=4, seed=0)
    summary = label_clusters(cluster_summary(labelled))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
