"""Smoke test: generate data, run all queries, assert sane results."""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "case-studies" / "01-funnel-and-retention"
sys.path.insert(0, str(CASE / "src"))

from generate_data import generate  # noqa: E402


def test_funnel_chains_each_step_after_prior_step():
    con = duckdb.connect()
    try:
        con.execute(
            """
            CREATE TABLE events AS
            SELECT * FROM (
                VALUES
                    (1, 'add_to_cart', TIMESTAMP '2024-01-01 09:59:00'),
                    (1, 'view_product', TIMESTAMP '2024-01-01 10:00:00'),
                    (1, 'checkout', TIMESTAMP '2024-01-01 10:01:00'),
                    (1, 'add_to_cart', TIMESTAMP '2024-01-01 10:02:00'),
                    (1, 'purchase', TIMESTAMP '2024-01-01 10:02:30'),
                    (1, 'checkout', TIMESTAMP '2024-01-01 10:03:00'),
                    (1, 'purchase', TIMESTAMP '2024-01-01 10:04:00'),
                    (2, 'view_product', TIMESTAMP '2024-01-01 11:00:00'),
                    (2, 'add_to_cart', TIMESTAMP '2024-01-01 11:05:00'),
                    (3, 'view_product', TIMESTAMP '2024-01-01 12:00:00'),
                    (3, 'purchase', TIMESTAMP '2024-01-01 12:05:00')
            ) AS t(user_id, event_name, event_time)
            """
        )

        funnel_sql = (CASE / "sql" / "01_funnel_overall.sql").read_text()
        viewed, carted, checkout, purchased, *_ = con.execute(funnel_sql).fetchone()
        assert (viewed, carted, checkout, purchased) == (3, 2, 1, 1)
    finally:
        con.close()


def test_retention_preserves_zero_activity_offsets():
    con = duckdb.connect()
    try:
        con.execute(
            """
            CREATE TABLE users AS
            SELECT * FROM (
                VALUES
                    (1, DATE '2024-01-01'),
                    (2, DATE '2024-01-01'),
                    (3, DATE '2024-01-08')
            ) AS t(user_id, signup_date)
            """
        )
        con.execute(
            """
            CREATE TABLE events AS
            SELECT * FROM (
                VALUES
                    (1, TIMESTAMP '2024-01-01 10:00:00'),
                    (1, TIMESTAMP '2024-01-15 10:00:00')
            ) AS t(user_id, event_time)
            """
        )

        ret_sql = (CASE / "sql" / "02_retention_weekly.sql").read_text()
        ret = con.execute(ret_sql).fetch_df()

        first_cohort = ret[ret["cohort_week"] == ret["cohort_week"].min()]
        assert len(first_cohort) == 12
        assert first_cohort.loc[first_cohort["week_offset"] == 1, "active_users"].item() == 0
        assert first_cohort.loc[first_cohort["week_offset"] == 1, "retention_pct"].item() == 0
        assert first_cohort.loc[first_cohort["week_offset"] == 2, "active_users"].item() == 1
    finally:
        con.close()


def test_generate_and_query_end_to_end():
    generate(n_users=2_000, seed=7)

    db_path = CASE / "data" / "ecommerce.db"
    assert db_path.exists()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        n_users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        n_events = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        assert n_users == 2_000
        assert n_events > 0

        # Run the funnel query
        funnel_sql = (CASE / "sql" / "01_funnel_overall.sql").read_text()
        funnel = con.execute(funnel_sql).fetchone()
        viewed, carted, checkout, purchased = funnel[0], funnel[1], funnel[2], funnel[3]

        # Monotonic funnel: each stage <= previous
        assert viewed >= carted >= checkout >= purchased
        assert viewed > 0
        # Cart rate should be roughly 35% +/- a fair bit of noise at n=2000
        assert 0.20 < carted / viewed < 0.50

        # Retention query returns rows
        ret_sql = (CASE / "sql" / "02_retention_weekly.sql").read_text()
        ret_rows = con.execute(ret_sql).fetchall()
        assert len(ret_rows) > 0

        # Device funnel returns one row per device
        dev_sql = (CASE / "sql" / "03_funnel_by_device.sql").read_text()
        dev_rows = con.execute(dev_sql).fetchall()
        assert len(dev_rows) == 3  # mobile, desktop, tablet
    finally:
        con.close()
