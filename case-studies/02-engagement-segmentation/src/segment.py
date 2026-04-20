"""
K-means engagement segmentation, complementary to RFM.

Pulls four engagement features per active user from DuckDB:
    views_28d, distinct_active_days_28d, purchase_count, total_revenue_cents

Standardizes, fits k-means with k=4, prints cluster centroids and sizes.

Why k=4?
    Empirically separates: dormant / casual / engaged / power user.
    Higher k tends to over-fragment with these 4 features; lower k collapses
    casual + engaged. For a shipped segmentation we'd validate k via
    silhouette/elbow + business interpretability, not blind selection.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
DB_PATH = HERE.parent.parent / "01-funnel-and-retention" / "data" / "ecommerce.db"


FEATURE_QUERY = """
WITH window_bounds AS (
    SELECT
        MAX(event_time)                       AS panel_end,
        MAX(event_time) - INTERVAL 28 DAY     AS window_start
    FROM events
),
features AS (
    SELECT
        e.user_id,
        COUNT(*) FILTER (WHERE e.event_name = 'view_product')              AS views_28d,
        COUNT(DISTINCT DATE_TRUNC('day', e.event_time))                    AS active_days_28d,
        COUNT(*) FILTER (WHERE e.event_name = 'purchase')                  AS purchase_count,
        COALESCE(SUM(e.revenue_cents) FILTER (WHERE e.event_name = 'purchase'), 0) AS revenue_cents
    FROM events e
    CROSS JOIN window_bounds w
    WHERE e.event_time >= w.window_start
    GROUP BY e.user_id
)
SELECT * FROM features WHERE views_28d > 0
"""


def load_features(db_path: Path = DB_PATH) -> pd.DataFrame:
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        return con.execute(FEATURE_QUERY).fetch_df()
    finally:
        con.close()


def fit_kmeans(
    features: pd.DataFrame,
    k: int = 4,
    seed: int = 0,
) -> tuple[pd.DataFrame, KMeans, StandardScaler]:
    """Fit standardized k-means; return features-with-cluster, model, scaler."""
    cols = ["views_28d", "active_days_28d", "purchase_count", "revenue_cents"]
    X = features[cols].to_numpy(dtype=float)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(Xs)
    out = features.copy()
    out["cluster"] = model.labels_
    return out, model, scaler


def cluster_summary(labelled: pd.DataFrame) -> pd.DataFrame:
    """Per-cluster mean of each feature and user count -- the table you'd put in a deck."""
    cols = ["views_28d", "active_days_28d", "purchase_count", "revenue_cents"]
    summary = (
        labelled.groupby("cluster")[cols].mean().round(2)
        .assign(n_users=labelled.groupby("cluster").size())
        .sort_values("revenue_cents", ascending=False)
        .reset_index()
    )
    summary["revenue_dollars"] = (summary["revenue_cents"] / 100).round(2)
    return summary[["cluster", "n_users", "views_28d", "active_days_28d",
                    "purchase_count", "revenue_dollars"]]


def label_clusters(summary: pd.DataFrame) -> pd.DataFrame:
    """Heuristic naming so the table reads like a memo, not numbers."""
    out = summary.copy()
    max_revenue = out["revenue_dollars"].max()
    names = []
    for _, row in out.iterrows():
        if row["revenue_dollars"] == max_revenue:
            names.append("power_users")
        elif row["purchase_count"] >= 1:
            names.append("engaged_buyers")
        elif row["active_days_28d"] >= 5:
            names.append("active_browsers")
        else:
            names.append("casual_visitors")
    out.insert(1, "segment", names)
    return out
