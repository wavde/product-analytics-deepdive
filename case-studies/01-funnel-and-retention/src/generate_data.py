"""
Generate a synthetic e-commerce event log for the funnel + retention case study.

Tables produced (loaded into a DuckDB database at data/ecommerce.db):

    users(user_id, signup_date, country, device)
    events(user_id, event_name, event_time, product_id, revenue_cents)

Events follow a realistic funnel:
    view_product -> add_to_cart -> checkout -> purchase
with per-step drop-off, and returning-user activity modeled by a Poisson
process per user to enable retention analysis.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DATA_DIR / "ecommerce.db"

START_DATE = datetime(2025, 1, 1)
END_DATE = datetime(2025, 3, 31)


def generate(n_users: int = 20_000, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    DATA_DIR.mkdir(exist_ok=True)

    # ---- users -----------------------------------------------------------
    signup_days = rng.integers(0, (END_DATE - START_DATE).days, size=n_users)
    users = pd.DataFrame(
        {
            "user_id": np.arange(1, n_users + 1, dtype=np.int64),
            "signup_date": [START_DATE + timedelta(days=int(d)) for d in signup_days],
            "country": rng.choice(["US", "GB", "DE", "IN", "BR"], size=n_users,
                                   p=[0.45, 0.12, 0.10, 0.20, 0.13]),
            "device": rng.choice(["mobile", "desktop", "tablet"], size=n_users,
                                  p=[0.60, 0.35, 0.05]),
        }
    )

    # ---- events ----------------------------------------------------------
    # Per-user activity level (sessions/week). Heavy-tailed.
    activity_rate = rng.gamma(shape=1.5, scale=2.0, size=n_users)

    rows: list[tuple] = []
    funnel_probs = {
        "view_product": 1.00,
        "add_to_cart":  0.35,
        "checkout":     0.55,   # conditional on cart
        "purchase":     0.70,   # conditional on checkout
    }

    for uid, signup, rate in zip(users["user_id"], users["signup_date"], activity_rate):
        days_active_max = (END_DATE - signup).days
        if days_active_max <= 0:
            continue
        # Expected number of sessions during the window
        n_sessions = int(rng.poisson(rate * days_active_max / 7.0))
        if n_sessions == 0:
            continue

        # Session start times (uniform between signup and end)
        session_offsets = rng.uniform(0, days_active_max, size=n_sessions)
        session_offsets.sort()

        for off in session_offsets:
            t0 = signup + timedelta(days=float(off),
                                    hours=float(rng.uniform(0, 24)))
            product_id = int(rng.integers(1, 1001))

            rows.append((int(uid), "view_product", t0, product_id, 0))
            if rng.random() < funnel_probs["add_to_cart"]:
                rows.append((int(uid), "add_to_cart",
                             t0 + timedelta(minutes=float(rng.uniform(1, 30))),
                             product_id, 0))
                if rng.random() < funnel_probs["checkout"]:
                    rows.append((int(uid), "checkout",
                                 t0 + timedelta(minutes=float(rng.uniform(5, 60))),
                                 product_id, 0))
                    if rng.random() < funnel_probs["purchase"]:
                        price = int(rng.gamma(2.0, 1500))  # cents, median ~$25
                        rows.append((int(uid), "purchase",
                                     t0 + timedelta(minutes=float(rng.uniform(10, 90))),
                                     product_id, price))

    events = pd.DataFrame(
        rows,
        columns=["user_id", "event_name", "event_time", "product_id", "revenue_cents"],
    )

    # ---- write to DuckDB -------------------------------------------------
    con = duckdb.connect(str(DB_PATH))
    con.execute("DROP TABLE IF EXISTS users")
    con.execute("DROP TABLE IF EXISTS events")
    con.register("users_df", users)
    con.register("events_df", events)
    con.execute("CREATE TABLE users AS SELECT * FROM users_df")
    con.execute("CREATE TABLE events AS SELECT * FROM events_df")
    con.close()

    print(f"Wrote {len(users):,} users and {len(events):,} events to {DB_PATH}")


if __name__ == "__main__":
    generate()
