"""Smoke test: case 02 SQL queries + k-means segmentation."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
CASE_01 = ROOT / "case-studies" / "01-funnel-and-retention"
CASE_02 = ROOT / "case-studies" / "02-engagement-segmentation"

sys.path.insert(0, str(CASE_01 / "src"))
sys.path.insert(0, str(CASE_02 / "src"))

from generate_data import generate  # noqa: E402
from segment import cluster_summary, fit_kmeans, label_clusters, load_features  # noqa: E402


def test_case_02_end_to_end():
    generate(n_users=2_000, seed=7)
    db_path = CASE_01 / "data" / "ecommerce.db"
    assert db_path.exists()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # Each SQL query should run and return rows.
        for name in ("01_rfm_scores.sql",
                     "02_power_user_curve.sql",
                     "03_revenue_concentration.sql"):
            sql = (CASE_02 / "sql" / name).read_text()
            df = con.execute(sql).fetch_df()
            assert len(df) > 0, f"{name} returned no rows"

        # Revenue concentration should sum to ~100%
        sql = (CASE_02 / "sql" / "03_revenue_concentration.sql").read_text()
        df = con.execute(sql).fetch_df()
        assert abs(df["pct_of_total_revenue"].sum() - 100) < 1.0
        # Top decile should hold the most revenue
        assert df.iloc[0]["pct_of_total_revenue"] > df.iloc[-1]["pct_of_total_revenue"]
    finally:
        con.close()

    # K-means runs and produces 4 non-empty clusters with names.
    features = load_features(db_path)
    assert len(features) > 0
    labelled, _, _ = fit_kmeans(features, k=4, seed=0)
    summary = label_clusters(cluster_summary(labelled))
    assert len(summary) == 4
    assert summary["n_users"].min() >= 1
    assert set(summary["segment"]).issubset(
        {"power_users", "engaged_buyers", "active_browsers", "casual_visitors"}
    )
