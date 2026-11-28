"""Case 04: warehouse traps, ground truth, answer key and evidence are correct and reproducible."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest
from analyst_eval import CASE_DIR
from analyst_eval.answer_key import HOLDOUT_KEY_PATH, compute_answer_key, load_answer_key
from analyst_eval.evidence import build_evidence, load_evidence
from analyst_eval.gold import Fixes, create_gold_views
from analyst_eval.memo_lint import lint_memo
from analyst_eval.questions import HOLDOUT_QUESTION_IDS, HOLDOUT_QUESTIONS, QUESTIONS, TOLERANCE

COMMITTED_KEY = load_answer_key()


@pytest.fixture(scope="module")
def fresh_key(analyst_db):
    return {r["id"]: r for r in compute_answer_key(analyst_db)}


def test_answer_key_reproduces_from_a_fresh_build(fresh_key):
    assert set(fresh_key) == set(COMMITTED_KEY) == {q.id for q in QUESTIONS}
    for qid, row in COMMITTED_KEY.items():
        fresh = fresh_key[qid]
        tol = TOLERANCE.get(row["unit"] or "", 0) / 10
        for field in ("gold", "naive"):
            if row[field] is None:
                assert fresh[field] is None, (qid, field)
            else:
                assert fresh[field] == pytest.approx(row[field], abs=tol), (qid, field)
        assert fresh["traps"] == row["traps"], qid
        assert fresh["naive_is_wrong"] == row["naive_is_wrong"], qid


def test_question_categories_mean_what_they_say():
    cats = [r["category"] for r in COMMITTED_KEY.values()]
    assert len(cats) == 40
    for r in COMMITTED_KEY.values():
        if r["category"] == "control":
            assert r["traps"] == [] and r["naive_is_wrong"] is False, r["id"]
        elif r["category"] in ("trap", "ambiguous"):
            assert r["traps"] and r["naive_is_wrong"] is True, r["id"]
            assert r["gold"] is not None
        else:
            assert r["expect_abstain"] and r["gold"] is None, r["id"]


def _tiny_warehouse() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    con.execute("""CREATE TABLE users AS SELECT * FROM (VALUES
        (1, DATE '2025-01-01', 'US', 'mobile', false),
        (2, DATE '2024-12-02', 'US', 'desktop', true)
    ) t(user_id, signup_date, country, device, is_internal)""")
    con.execute("""CREATE TABLE events AS SELECT * FROM (VALUES
        ('e1', 1, 'purchase', TIMESTAMP '2025-03-01 07:30', TIMESTAMP '2025-03-01 07:30:02',
         7, 'o1', 500),
        ('e1', 1, 'purchase', TIMESTAMP '2025-03-01 07:30', TIMESTAMP '2025-03-01 07:31:00',
         7, 'o1', 500),
        ('s1', 1, 'email_delivered', TIMESTAMP '2025-03-04 17:00', TIMESTAMP '2025-03-04 17:00',
         NULL, NULL, 0),
        ('e3', 2, 'purchase', TIMESTAMP '2025-03-04 20:00', TIMESTAMP '2025-03-04 20:00:01',
         8, 'o2', 900),
        ('e4', 1, 'view_product', TIMESTAMP '2025-03-10 07:30', TIMESTAMP '2025-03-10 07:30',
         9, NULL, 0)
    ) t(event_id, user_id, event_name, event_ts, ingested_at, product_id, order_id,
        revenue_cents)""")
    con.execute("""CREATE TABLE refunds AS SELECT * FROM (VALUES
        ('r1', 'o1', TIMESTAMP '2025-03-20 12:00', 200)
    ) t(refund_id, order_id, refund_ts, refund_cents)""")
    return con


def test_timestamps_round_half_up_to_microseconds_on_every_engine():
    import pandas as pd
    from analyst_eval.warehouse import _to_microseconds

    s = pd.Series(pd.to_datetime(["2025-01-01 00:00:00.000000499",
                                  "2025-01-01 00:00:00.000000500",
                                  "2025-01-01 00:00:00.000001999", None]))
    out = _to_microseconds(s)
    assert list(out[:3].astype("int64") % 10**6) == [0, 1, 2]
    assert pd.isna(out[3])


def test_gold_views_apply_every_ground_rule():
    con = _tiny_warehouse()
    create_gold_views(con)
    rows = con.execute("SELECT event_id, biz_date FROM g_events ORDER BY event_id").fetchall()
    # e1 once (dedup), s1 dropped (system), e3 dropped (internal);
    # 07:30 UTC on 1 Mar is 23:30 PST on 28 Feb; 07:30 UTC on 10 Mar is 00:30 PDT on 10 Mar.
    assert rows == [("e1", date(2025, 2, 28)), ("e4", date(2025, 3, 10))]
    order = con.execute("SELECT order_date, gross_cents, refund_cents, net_cents FROM g_orders")
    assert order.fetchall() == [(date(2025, 2, 28), 500, 200, 300)]


@pytest.mark.parametrize("rule, expected_events", [
    ("duplicates", 3), ("system_events", 3), ("internal_accounts", 3), ("timezone", 2),
])
def test_each_fix_can_be_switched_off_independently(rule, expected_events):
    con = _tiny_warehouse()
    create_gold_views(con, Fixes().without(rule))
    assert con.execute("SELECT COUNT(*) FROM g_events").fetchone()[0] == expected_events
    if rule == "timezone":
        dates = con.execute("SELECT biz_date FROM g_events ORDER BY event_id").fetchall()
        assert dates == [(date(2025, 3, 1),), (date(2025, 3, 10),)]


def test_resubmitted_order_counts_once_and_only_its_rule_lets_it_back_in():
    con = _tiny_warehouse()
    con.execute("""INSERT INTO events VALUES ('e5', 1, 'purchase', TIMESTAMP '2025-03-01 07:31',
                   TIMESTAMP '2025-03-01 07:31:02', 7, 'o1', 500)""")
    orders = "SELECT COUNT(*), SUM(gross_cents) FROM g_orders"
    create_gold_views(con)
    assert con.execute(orders).fetchone() == (1, 500)
    create_gold_views(con, Fixes().without("duplicates"))
    assert con.execute(orders).fetchone() == (2, 1000)  # e1's retry row is back; e5 is not
    create_gold_views(con, Fixes().without("resubmitted_orders"))
    assert con.execute(orders).fetchone() == (2, 1000)  # e5 is back; e1's retry is not


@pytest.fixture(scope="module")
def holdout_full_key(holdout_db):
    return {r["id"]: r for r in compute_answer_key(holdout_db)}


def test_holdout_changes_only_what_it_should(holdout_full_key):
    live = {q for q, r in holdout_full_key.items() if "resubmitted_orders" in r["traps"]}
    assert live == set(HOLDOUT_QUESTION_IDS)
    assert "resubmitted_orders" not in {t for r in COMMITTED_KEY.values() for t in r["traps"]}
    # Every other question keeps its main-warehouse gold, except t13: it counts purchase
    # *events*, and a re-submission is a distinct event, so it is left out of the holdout set.
    moved = {q for q, row in COMMITTED_KEY.items() if holdout_full_key[q]["gold"] != row["gold"]}
    assert moved == {"t13"}


def test_holdout_answer_key_reproduces(holdout_db):
    committed = load_answer_key(HOLDOUT_KEY_PATH)
    fresh = {r["id"]: r for r in compute_answer_key(holdout_db, HOLDOUT_QUESTIONS)}
    assert list(committed) == list(fresh) == list(HOLDOUT_QUESTION_IDS)
    for qid, row in committed.items():
        tol = TOLERANCE.get(row["unit"] or "", 0) / 10
        assert fresh[qid]["gold"] == pytest.approx(row["gold"], abs=tol), qid
        assert fresh[qid]["naive"] == pytest.approx(row["naive"], abs=tol), qid
        assert fresh[qid]["traps"] == row["traps"], qid


def test_gold_reconciles_with_an_independent_pandas_route(analyst_db):
    """The reconcile-results skill applied to our own ground truth."""
    con = duckdb.connect(str(analyst_db), read_only=True)
    users = con.execute("SELECT * FROM users").fetch_df()
    events = con.execute("SELECT * FROM events").fetch_df()
    refunds = con.execute("SELECT * FROM refunds").fetch_df()
    con.close()

    ev = events.sort_values("ingested_at").drop_duplicates("event_id")
    ev = ev[ev["event_name"].isin(["view_product", "add_to_cart", "checkout", "purchase"])]
    ev = ev.merge(users.loc[~users["is_internal"], ["user_id", "device"]], on="user_id")
    local = ev["event_ts"].dt.tz_localize("UTC").dt.tz_convert("America/Los_Angeles")
    ev["biz_date"] = local.dt.date
    orders = ev[ev["event_name"] == "purchase"].merge(
        refunds.groupby("order_id", as_index=False)["refund_cents"].sum(), on="order_id",
        how="left").fillna({"refund_cents": 0})

    def between(s, a, b):
        return (s >= date.fromisoformat(a)) & (s <= date.fromisoformat(b))

    feb = orders[between(orders["biz_date"], "2025-02-01", "2025-02-28")]
    cohort = users.loc[~users["is_internal"] & between(
        users["signup_date"].dt.date, "2025-01-13", "2025-01-19"), "user_id"]
    active = set(ev.loc[between(ev["biz_date"], "2025-01-20", "2025-01-26"), "user_id"])
    independent = {
        "t01": len(feb),
        "t03": (feb["revenue_cents"].sum() - feb["refund_cents"].sum()) / 100,
        "t06": ev.loc[ev["biz_date"] == date(2025, 3, 4), "user_id"].nunique(),
        "a08": 100 * cohort.isin(active).mean(),
    }
    for qid, value in independent.items():
        assert value == pytest.approx(COMMITTED_KEY[qid]["gold"], abs=1e-3), qid


def test_evidence_reproduces_and_readme_claims_match_it(analyst_db, holdout_db):
    committed = load_evidence()
    fresh = build_evidence(analyst_db, holdout_db_path=holdout_db)
    assert set(fresh) == set(committed)
    for k, entry in committed.items():
        assert fresh[k]["value"] == pytest.approx(entry["value"], abs=1e-3), k
    readme = (CASE_DIR / "README.md").read_text(encoding="utf-8")
    issues = lint_memo(readme, committed)
    assert not issues, "\n".join(str(i) for i in issues)
