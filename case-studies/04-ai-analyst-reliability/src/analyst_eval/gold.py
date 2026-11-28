"""Ground-truth layer: the metric definitions in ``context/definitions.md`` as DuckDB views.

Each data-cleaning rule can be switched off independently. Recomputing a gold answer with
one rule disabled tells us, empirically, whether that trap actually moves that question's
answer -- so trap tags on the question set are measured rather than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

import duckdb

BUSINESS_TZ = "America/Los_Angeles"
USER_EVENTS_SQL = "('view_product', 'add_to_cart', 'checkout', 'purchase')"


@dataclass(frozen=True)
class Fixes:
    """Which cleaning rules the gold views apply. All on = the documented definitions."""

    duplicates: bool = True
    internal_accounts: bool = True
    system_events: bool = True
    timezone: bool = True
    # One order per order_id ("Order ... identified by order_id" in definitions.md). A no-op
    # on the main warehouse, where every order_id has one purchase event; it matters on the
    # holdout warehouse, where some purchases were re-submitted under a new event_id.
    resubmitted_orders: bool = True

    @classmethod
    def names(cls) -> list[str]:
        return [f.name for f in fields(cls)]

    def without(self, name: str) -> Fixes:
        return Fixes(**{**self.__dict__, name: False})


def create_gold_views(con: duckdb.DuckDBPyConnection, fixes: Fixes = Fixes()) -> None:
    dedup = (
        "QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY ingested_at, event_ts) = 1"
        if fixes.duplicates
        else ""
    )
    internal = "WHERE NOT is_internal" if fixes.internal_accounts else ""
    system = f"AND d.event_name IN {USER_EVENTS_SQL}" if fixes.system_events else ""
    local_ts = (
        f"(d.event_ts AT TIME ZONE 'UTC' AT TIME ZONE '{BUSINESS_TZ}')"
        if fixes.timezone
        else "d.event_ts"
    )
    con.execute(f"CREATE OR REPLACE TEMP VIEW g_users AS SELECT * FROM users {internal}")
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW g_events AS
        WITH d AS (SELECT * FROM events {dedup})
        SELECT d.event_id, d.user_id, d.event_name, d.event_ts, d.product_id, d.order_id,
               d.revenue_cents,
               {local_ts}             AS biz_ts,
               CAST({local_ts} AS DATE) AS biz_date
        FROM d
        JOIN g_users u ON u.user_id = d.user_id
        WHERE TRUE {system}
        """
    )
    # Keep only the order's first submission (its earliest event_id). Same-event_id retries are
    # left to the duplicates rule, so switching either rule off measures that trap alone.
    first_submission = "WHERE event_id = first_event_id" if fixes.resubmitted_orders else ""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP VIEW g_orders AS
        WITH p AS (
            SELECT *, FIRST_VALUE(event_id) OVER (
                       PARTITION BY order_id ORDER BY event_ts, event_id) AS first_event_id
            FROM g_events WHERE event_name = 'purchase'
        )
        SELECT e.order_id,
               e.user_id,
               e.biz_date                                  AS order_date,
               e.revenue_cents                             AS gross_cents,
               COALESCE(r.refund_cents, 0)                 AS refund_cents,
               e.revenue_cents - COALESCE(r.refund_cents, 0) AS net_cents
        FROM (SELECT * FROM p {first_submission}) e
        LEFT JOIN (
            SELECT order_id, SUM(refund_cents) AS refund_cents FROM refunds GROUP BY order_id
        ) r ON r.order_id = e.order_id
        """
    )
