"""Build the case-04 analytics warehouse: case 01's simulated store plus realistic data traps.

The organic behaviour comes from case 01's generator (unchanged). On top of it this
module layers the kinds of mess a real event warehouse accumulates, each of which is
documented in ``context/traps.md``:

* client retries that re-send an event with the same ``event_id`` (duplicates)
* QA accounts that place test orders every business day (internal traffic)
* system-generated ``email_delivered`` / ``push_delivered`` rows in the events table
* UTC timestamps, while the business reports in America/Los_Angeles
* refunds in a separate table, landing days to weeks after the order
* a load watermark part-way through the final day (partial period)

Tables written to ``data/analyst.db``:

    users(user_id, signup_date, country, device, is_internal)
    events(event_id, user_id, event_name, event_ts, ingested_at, product_id, order_id,
           revenue_cents)
    refunds(refund_id, order_id, refund_ts, refund_cents)
    etl_watermark(table_name, loaded_through)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from analyst_eval import DB_PATH, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "case-studies" / "01-funnel-and-retention" / "src"))
from generate_data import simulate  # noqa: E402

DEFAULT_N_USERS = 5_000
DEFAULT_SEED = 7

WINDOW_START = pd.Timestamp("2025-01-01")
WATERMARK = pd.Timestamp("2025-03-31 18:00:00")  # UTC; 11:00 on 2025-03-31 in Los Angeles

N_QA_ACCOUNTS = 10
QA_FIRST_ID = 900_001
QA_ORDERS_PER_DAY = 2.0
DUPLICATE_RATE = 0.04
REFUND_RATE = 0.08
FULL_REFUND_SHARE = 0.75
PUSH_REACH = 0.40

USER_EVENTS = ("view_product", "add_to_cart", "checkout", "purchase")
SYSTEM_EVENTS = ("email_delivered", "push_delivered")


def _qa_events(rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    qa_users = pd.DataFrame(
        {
            "user_id": np.arange(QA_FIRST_ID, QA_FIRST_ID + N_QA_ACCOUNTS, dtype=np.int64),
            "signup_date": pd.Timestamp("2024-12-02"),
            "country": "US",
            "device": "desktop",
        }
    )
    rows: list[tuple] = []
    for day in pd.date_range(WINDOW_START, WATERMARK.normalize(), freq="D"):
        if day.weekday() >= 5:  # QA runs on weekdays only
            continue
        for uid in qa_users["user_id"]:
            for _ in range(int(rng.poisson(QA_ORDERS_PER_DAY))):
                # 07:00-16:00 Pacific is 15:00-24:00 UTC in winter
                t0 = day + pd.Timedelta(hours=float(rng.uniform(15, 24)))
                pid = int(rng.integers(1, 1001))
                price = int(rng.gamma(2.0, 1500))
                rows.append((int(uid), "view_product", t0, pid, 0))
                rows.append((int(uid), "add_to_cart", t0 + pd.Timedelta(minutes=1), pid, 0))
                rows.append((int(uid), "checkout", t0 + pd.Timedelta(minutes=2), pid, 0))
                rows.append((int(uid), "purchase", t0 + pd.Timedelta(minutes=3), pid, price))
    events = pd.DataFrame(
        rows, columns=["user_id", "event_name", "event_time", "product_id", "revenue_cents"]
    )
    return qa_users, events


def _system_events(users: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    frames = []
    # Weekly lifecycle email, sent Tuesdays 17:00 UTC to everyone signed up by then.
    for send in pd.date_range("2025-01-07 17:00", WATERMARK, freq="7D"):
        eligible = users.loc[users["signup_date"] <= send.normalize(), "user_id"]
        jitter = pd.to_timedelta(rng.uniform(0, 600, size=len(eligible)), unit="s")
        frames.append(
            pd.DataFrame({"user_id": eligible.to_numpy(), "event_name": "email_delivered",
                          "event_time": send + jitter})
        )
    # Weekly push, sent Fridays 02:00 UTC (Thursday evening in Los Angeles) to mobile users.
    mobile = users[users["device"] == "mobile"]
    for send in pd.date_range("2025-01-03 02:00", WATERMARK, freq="7D"):
        eligible = mobile.loc[mobile["signup_date"] <= send.normalize(), "user_id"]
        reached = eligible[rng.random(len(eligible)) < PUSH_REACH]
        jitter = pd.to_timedelta(rng.uniform(0, 300, size=len(reached)), unit="s")
        frames.append(
            pd.DataFrame({"user_id": reached.to_numpy(), "event_name": "push_delivered",
                          "event_time": send + jitter})
        )
    out = pd.concat(frames, ignore_index=True)
    out["product_id"] = pd.NA
    out["revenue_cents"] = 0
    return out


def build_frames(
    n_users: int = DEFAULT_N_USERS, seed: int = DEFAULT_SEED
) -> dict[str, pd.DataFrame]:
    users, organic = simulate(n_users=n_users, seed=seed)
    rng = np.random.default_rng([seed, 4])

    users = users.assign(is_internal=False)
    qa_users, qa_events = _qa_events(rng)
    users = pd.concat([users, qa_users.assign(is_internal=True)], ignore_index=True)
    users["signup_date"] = pd.to_datetime(users["signup_date"]).dt.normalize()

    user_events = pd.concat([organic, qa_events], ignore_index=True)
    user_events = user_events.sort_values(["event_time", "user_id"], kind="stable")
    user_events = user_events[user_events["event_time"] <= WATERMARK].reset_index(drop=True)
    user_events["product_id"] = user_events["product_id"].astype("Int64")
    user_events["event_id"] = [f"ev_{i:07d}" for i in range(len(user_events))]
    is_purchase = user_events["event_name"] == "purchase"
    user_events["order_id"] = pd.Series(pd.NA, index=user_events.index, dtype="string")
    user_events.loc[is_purchase, "order_id"] = [f"ord_{i:06d}" for i in range(is_purchase.sum())]

    system = _system_events(users, rng)
    system = system[system["event_time"] <= WATERMARK].sort_values(["event_time", "user_id"])
    system = system.reset_index(drop=True)
    system["product_id"] = system["product_id"].astype("Int64")
    system["event_id"] = [f"sys_{i:07d}" for i in range(len(system))]
    system["order_id"] = pd.Series(pd.NA, index=system.index, dtype="string")

    events = pd.concat([user_events, system], ignore_index=True)
    events["ingested_at"] = events["event_time"] + pd.to_timedelta(
        rng.uniform(0.5, 5.0, size=len(events)), unit="s"
    )

    # Client retries: same event (same event_id / order_id), ingested again later.
    retry_mask = events["event_name"].isin(USER_EVENTS).to_numpy() & (
        rng.random(len(events)) < DUPLICATE_RATE
    )
    retries = events[retry_mask].copy()
    retries["ingested_at"] = retries["ingested_at"] + pd.to_timedelta(
        rng.uniform(1, 120, size=len(retries)), unit="s"
    )
    events = pd.concat([events, retries], ignore_index=True)
    events = events.sort_values(["ingested_at", "event_id"], kind="stable").reset_index(drop=True)
    events = events.rename(columns={"event_time": "event_ts"})[
        ["event_id", "user_id", "event_name", "event_ts", "ingested_at", "product_id",
         "order_id", "revenue_cents"]
    ]

    # Refunds on real (non-QA) orders, landing 1-21 days after purchase.
    orders = user_events.loc[
        is_purchase & (user_events["user_id"] < QA_FIRST_ID),
        ["order_id", "event_time", "revenue_cents"],
    ]
    refunded = orders[rng.random(len(orders)) < REFUND_RATE].copy()
    full = rng.random(len(refunded)) < FULL_REFUND_SHARE
    partial_share = rng.uniform(0.3, 0.7, size=len(refunded))
    refunded["refund_cents"] = np.where(
        full, refunded["revenue_cents"], np.round(refunded["revenue_cents"] * partial_share)
    ).astype(np.int64)
    refunded["refund_ts"] = refunded["event_time"] + pd.to_timedelta(
        rng.uniform(1, 21, size=len(refunded)), unit="D"
    )
    refunded = refunded[(refunded["refund_ts"] <= WATERMARK) & (refunded["refund_cents"] > 0)]
    refunds = refunded.sort_values("refund_ts").reset_index(drop=True)
    refunds["refund_id"] = [f"rf_{i:05d}" for i in range(len(refunds))]
    refunds = refunds[["refund_id", "order_id", "refund_ts", "refund_cents"]]

    watermark = pd.DataFrame(
        {"table_name": ["events", "refunds"], "loaded_through": [WATERMARK, WATERMARK]}
    )
    return {"users": users, "events": events, "refunds": refunds, "etl_watermark": watermark}


def write_warehouse(frames: dict[str, pd.DataFrame], db_path: Path | str) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    try:
        for name, df in frames.items():
            con.execute(f"DROP TABLE IF EXISTS {name}")
            con.register(f"{name}_df", df)
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM {name}_df")
            con.unregister(f"{name}_df")
        con.execute("ALTER TABLE users ALTER signup_date TYPE DATE")
        con.execute("ALTER TABLE events ALTER event_ts TYPE TIMESTAMP")
        con.execute("ALTER TABLE events ALTER ingested_at TYPE TIMESTAMP")
        con.execute("ALTER TABLE refunds ALTER refund_ts TYPE TIMESTAMP")
        con.execute("ALTER TABLE etl_watermark ALTER loaded_through TYPE TIMESTAMP")
    finally:
        con.close()


def build(
    db_path: Path | str = DB_PATH, n_users: int = DEFAULT_N_USERS, seed: int = DEFAULT_SEED
) -> Path:
    frames = build_frames(n_users=n_users, seed=seed)
    write_warehouse(frames, db_path)
    return Path(db_path)


def connect_readonly(db_path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    """Read-only connection with external access disabled and a pinned UTC session zone."""
    con = duckdb.connect(str(db_path), read_only=True)
    con.execute("SET TimeZone = 'UTC'")  # autoloads ICU before external access is disabled
    # One thread makes unordered results and float sums reproducible run to run, which is
    # what lets a saved run be replayed and checked.
    con.execute("SET threads = 1")
    con.execute("SET enable_external_access = false")
    con.execute("SET lock_configuration = true")
    return con


if __name__ == "__main__":
    t0 = datetime.now()
    path = build()
    print(f"Wrote warehouse to {path} in {(datetime.now() - t0).total_seconds():.1f}s")
