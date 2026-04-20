"""Smoke test: case 03 north-star SQL queries."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
CASE_01 = ROOT / "case-studies" / "01-funnel-and-retention"
CASE_03 = ROOT / "case-studies" / "03-north-star-metric"

sys.path.insert(0, str(CASE_01 / "src"))
from generate_data import generate  # noqa: E402


def test_case_03_north_star_queries():
    generate(n_users=2_000, seed=7)
    db_path = CASE_01 / "data" / "ecommerce.db"
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        ns_sql = (CASE_03 / "sql" / "01_north_star_daily.sql").read_text()
        ns = con.execute(ns_sql).fetch_df()
        assert len(ns) > 0
        # Every row should have a non-negative WPAU
        assert (ns["wpau"] >= 0).all()
        # Most days should have at least one purchaser
        assert (ns["wpau"] > 0).sum() > len(ns) * 0.5

        decomp_sql = (CASE_03 / "sql" / "02_decomposition.sql").read_text()
        decomp = con.execute(decomp_sql).fetch_df()
        assert set(decomp["period"]) == {"this_week", "prev_week"}
        # WPAU should be <= WAU in both periods
        for _, row in decomp.iterrows():
            assert row["wpau"] <= row["wau"]
            # Conversion should be a percentage in [0, 100]
            assert 0 <= row["purchase_conversion_pct"] <= 100
    finally:
        con.close()
