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
    con.execute(
        """
        CREATE OR REPLACE TEMP VIEW g_orders AS
        SELECT e.order_id,
               e.user_id,
               e.biz_date                                  AS order_date,
               e.revenue_cents                             AS gross_cents,
               COALESCE(r.refund_cents, 0)                 AS refund_cents,
               e.revenue_cents - COALESCE(r.refund_cents, 0) AS net_cents
        FROM g_events e
        LEFT JOIN (
            SELECT order_id, SUM(refund_cents) AS refund_cents FROM refunds GROUP BY order_id
        ) r ON r.order_id = e.order_id
        WHERE e.event_name = 'purchase'
        """
    )
