"""The graded question set.

Each question carries:

* ``gold_sql`` -- the answer under the documented definitions, written against the
  ``g_*`` views in :mod:`analyst_eval.gold`. Never shown to the model.
* ``naive_sql`` -- a plausible first draft against the raw tables, the query a competent
  analyst new to this warehouse might write. Used to measure how far each trap moves the
  number and to classify wrong model answers as "fell for the trap" vs. something else.
* ``traps`` -- semantic traps that aren't data-cleaning rules (refund attribution, units,
  partial periods, ambiguous wording, uninstrumented data). Data-cleaning traps
  (duplicates, internal accounts, system events, time zone) are measured per question by
  :mod:`analyst_eval.answer_key`, not declared here.

Categories: ``control`` (no trap should move the answer), ``trap`` (unambiguous wording,
messy data), ``ambiguous`` (wording that the definitions resolve), ``unanswerable``
(the correct behaviour is to abstain).
"""

from __future__ import annotations

from dataclasses import dataclass, field

TOLERANCE = {"count": 0.5, "usd": 1.0, "percent": 0.05, "ratio": 0.005}


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    question: str
    unit: str | None
    gold_sql: str | None
    naive_sql: str | None = None
    traps: tuple[str, ...] = field(default_factory=tuple)

    @property
    def expect_abstain(self) -> bool:
        return self.category == "unanswerable"

    @property
    def tolerance(self) -> float | None:
        return TOLERANCE[self.unit] if self.unit else None


FEB = "BETWEEN DATE '2025-02-01' AND DATE '2025-02-28'"
JAN = "BETWEEN DATE '2025-01-01' AND DATE '2025-01-31'"
FEB_UTC = "event_ts >= TIMESTAMP '2025-02-01' AND event_ts < TIMESTAMP '2025-03-01'"
JAN_UTC = "event_ts >= TIMESTAMP '2025-01-01' AND event_ts < TIMESTAMP '2025-02-01'"

QUESTIONS: list[Question] = [
    # ---- controls ---------------------------------------------------------------------
    Question(
        "c01", "control", "How many users are based in Germany (country code DE)?", "count",
        "SELECT COUNT(*) FROM g_users WHERE country = 'DE'",
        "SELECT COUNT(*) FROM users WHERE country = 'DE'",
    ),
    Question(
        "c02", "control", "How many users signed up on 2025-02-14?", "count",
        "SELECT COUNT(*) FROM g_users WHERE signup_date = DATE '2025-02-14'",
        "SELECT COUNT(*) FROM users WHERE signup_date = DATE '2025-02-14'",
    ),
    Question(
        "c03", "control",
        "How many distinct products were added to a cart at least once in the data?", "count",
        "SELECT COUNT(DISTINCT product_id) FROM g_events WHERE event_name = 'add_to_cart'",
        "SELECT COUNT(DISTINCT product_id) FROM events WHERE event_name = 'add_to_cart'",
    ),
    Question(
        "c04", "control", "How many users signed up in January 2025 on a mobile device?",
        "count",
        f"SELECT COUNT(*) FROM g_users WHERE device = 'mobile' AND signup_date {JAN}",
        f"SELECT COUNT(*) FROM users WHERE device = 'mobile' AND signup_date {JAN}",
    ),
    Question(
        "c05", "control",
        "How many users from India (country code IN) signed up between 2025-03-01 and "
        "2025-03-30?",
        "count",
        "SELECT COUNT(*) FROM g_users WHERE country = 'IN' "
        "AND signup_date BETWEEN DATE '2025-03-01' AND DATE '2025-03-30'",
        "SELECT COUNT(*) FROM users WHERE country = 'IN' "
        "AND signup_date BETWEEN DATE '2025-03-01' AND DATE '2025-03-30'",
    ),
    Question(
        "c06", "control",
        "What was the average order value (gross) in February 2025, in US dollars?",
        "usd",
        f"SELECT SUM(gross_cents) / 100.0 / COUNT(*) FROM g_orders WHERE order_date {FEB}",
        f"SELECT AVG(revenue_cents) / 100.0 FROM events "
        f"WHERE event_name = 'purchase' AND {FEB_UTC}",
    ),
    Question(
        "c07", "control", "What percent of users signed up on a tablet?", "percent",
        "SELECT 100.0 * COUNT(*) FILTER (WHERE device = 'tablet') / COUNT(*) FROM g_users",
        "SELECT 100.0 * COUNT(*) FILTER (WHERE device = 'tablet') / COUNT(*) FROM users",
    ),
    # ---- traps: unambiguous wording, messy data ------------------------------------------
    Question(
        "t01", "trap", "How many orders were placed in February 2025?", "count",
        f"SELECT COUNT(*) FROM g_orders WHERE order_date {FEB}",
        f"SELECT COUNT(*) FROM events WHERE event_name = 'purchase' AND {FEB_UTC}",
    ),
    Question(
        "t02", "trap", "What was gross revenue in February 2025, in US dollars?", "usd",
        f"SELECT SUM(gross_cents) / 100.0 FROM g_orders WHERE order_date {FEB}",
        f"SELECT SUM(revenue_cents) / 100.0 FROM events "
        f"WHERE event_name = 'purchase' AND {FEB_UTC}",
    ),
    Question(
        "t03", "trap",
        "What was net revenue (gross revenue minus refunds) in February 2025, in US dollars?",
        "usd",
        f"SELECT SUM(net_cents) / 100.0 FROM g_orders WHERE order_date {FEB}",
        f"""SELECT ((SELECT SUM(revenue_cents) FROM events
                     WHERE event_name = 'purchase' AND {FEB_UTC})
                  - (SELECT SUM(refund_cents) FROM refunds
                     WHERE refund_ts >= TIMESTAMP '2025-02-01'
                       AND refund_ts < TIMESTAMP '2025-03-01')) / 100.0""",
        ("refunds",),
    ),
    Question(
        "t04", "trap",
        "What was total net revenue (after refunds) from 2025-01-01 through 2025-03-30, "
        "in US dollars?",
        "usd",
        "SELECT SUM(net_cents) / 100.0 FROM g_orders "
        "WHERE order_date BETWEEN DATE '2025-01-01' AND DATE '2025-03-30'",
        """SELECT ((SELECT SUM(revenue_cents) FROM events WHERE event_name = 'purchase'
                     AND event_ts >= TIMESTAMP '2025-01-01' AND event_ts < TIMESTAMP '2025-03-31')
                  - (SELECT SUM(refund_cents) FROM refunds
                     WHERE refund_ts >= TIMESTAMP '2025-01-01'
                       AND refund_ts < TIMESTAMP '2025-03-31')) / 100.0""",
        ("refunds",),
    ),
    Question(
        "t05", "trap",
        "For orders placed in January 2025, what percent of gross revenue was refunded?",
        "percent",
        f"SELECT 100.0 * SUM(refund_cents) / SUM(gross_cents) FROM g_orders "
        f"WHERE order_date {JAN}",
        f"""SELECT 100.0 * (SELECT SUM(refund_cents) FROM refunds
                            WHERE refund_ts >= TIMESTAMP '2025-01-01'
                              AND refund_ts < TIMESTAMP '2025-02-01')
                 / (SELECT SUM(revenue_cents) FROM events
                    WHERE event_name = 'purchase' AND {JAN_UTC})""",
        ("refunds",),
    ),
    Question(
        "t06", "trap", "How many daily active users were there on 2025-03-04?", "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date = DATE '2025-03-04'",
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE CAST(event_ts AS DATE) = "
        "DATE '2025-03-04'",
    ),
    Question(
        "t07", "trap", "How many daily active users were there on 2025-03-13?", "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date = DATE '2025-03-13'",
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE CAST(event_ts AS DATE) = "
        "DATE '2025-03-13'",
    ),
    Question(
        "t08", "trap",
        "How many weekly active users were there in the week of Monday 2025-03-17 "
        "through Sunday 2025-03-23?",
        "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_events "
        "WHERE biz_date BETWEEN DATE '2025-03-17' AND DATE '2025-03-23'",
        "SELECT COUNT(DISTINCT user_id) FROM events "
        "WHERE event_ts >= TIMESTAMP '2025-03-17' AND event_ts < TIMESTAMP '2025-03-24'",
    ),
    Question(
        "t09", "trap", "How many monthly active users were there in January 2025?", "count",
        f"SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date {JAN}",
        f"SELECT COUNT(DISTINCT user_id) FROM events WHERE {JAN_UTC}",
    ),
    Question(
        "t10", "trap",
        "How many distinct users made at least one purchase between 2025-03-01 and 2025-03-30?",
        "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_orders "
        "WHERE order_date BETWEEN DATE '2025-03-01' AND DATE '2025-03-30'",
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_name = 'purchase' "
        "AND event_ts >= TIMESTAMP '2025-03-01' AND event_ts < TIMESTAMP '2025-03-31'",
    ),
    Question(
        "t11", "trap",
        "In the week of Monday 2025-02-10 through Sunday 2025-02-16, what percent of weekly "
        "active users made a purchase?",
        "percent",
        """SELECT 100.0 * COUNT(DISTINCT CASE WHEN event_name = 'purchase' THEN user_id END)
                 / COUNT(DISTINCT user_id)
           FROM g_events WHERE biz_date BETWEEN DATE '2025-02-10' AND DATE '2025-02-16'""",
        """SELECT 100.0 * COUNT(DISTINCT CASE WHEN event_name = 'purchase' THEN user_id END)
                 / COUNT(DISTINCT user_id)
           FROM events
           WHERE event_ts >= TIMESTAMP '2025-02-10' AND event_ts < TIMESTAMP '2025-02-17'""",
    ),
    Question(
        "t12", "trap", "How many add-to-cart actions happened on 2025-02-14?", "count",
        "SELECT COUNT(*) FROM g_events WHERE event_name = 'add_to_cart' "
        "AND biz_date = DATE '2025-02-14'",
        "SELECT COUNT(*) FROM events WHERE event_name = 'add_to_cart' "
        "AND CAST(event_ts AS DATE) = DATE '2025-02-14'",
    ),
    Question(
        "t13", "trap",
        "How many user actions (product views, add-to-carts, checkouts and purchases) were "
        "recorded in January 2025?",
        "count",
        f"SELECT COUNT(*) FROM g_events WHERE biz_date {JAN}",
        f"SELECT COUNT(*) FROM events WHERE {JAN_UTC} AND event_name IN "
        "('view_product', 'add_to_cart', 'checkout', 'purchase')",
    ),
    Question(
        "t14", "trap",
        "What was WPAU (distinct purchasers in the trailing 7 days, inclusive) on 2025-03-15?",
        "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_orders "
        "WHERE order_date BETWEEN DATE '2025-03-09' AND DATE '2025-03-15'",
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_name = 'purchase' "
        "AND CAST(event_ts AS DATE) BETWEEN DATE '2025-03-09' AND DATE '2025-03-15'",
    ),
    Question(
        "t15", "trap", "How many orders placed in February 2025 received any refund?", "count",
        f"SELECT COUNT(*) FROM g_orders WHERE order_date {FEB} AND refund_cents > 0",
        "SELECT COUNT(*) FROM refunds "
        "WHERE refund_ts >= TIMESTAMP '2025-02-01' AND refund_ts < TIMESTAMP '2025-03-01'",
        ("refunds",),
    ),
    Question(
        "t16", "trap",
        "Of users who signed up between Monday 2025-01-06 and Sunday 2025-01-12, what percent "
        "were active in the following week (2025-01-13 through 2025-01-19)?",
        "percent",
        """WITH cohort AS (SELECT user_id FROM g_users
                          WHERE signup_date BETWEEN DATE '2025-01-06' AND DATE '2025-01-12'),
                active AS (SELECT DISTINCT user_id FROM g_events
                           WHERE biz_date BETWEEN DATE '2025-01-13' AND DATE '2025-01-19')
           SELECT 100.0 * COUNT(a.user_id) / COUNT(*)
           FROM cohort c LEFT JOIN active a USING (user_id)""",
        """WITH cohort AS (SELECT user_id FROM users
                          WHERE signup_date BETWEEN DATE '2025-01-06' AND DATE '2025-01-12'),
                active AS (SELECT DISTINCT user_id FROM events
                           WHERE event_ts >= TIMESTAMP '2025-01-13'
                             AND event_ts < TIMESTAMP '2025-01-20')
           SELECT 100.0 * COUNT(a.user_id) / COUNT(*)
           FROM cohort c LEFT JOIN active a USING (user_id)""",
    ),
    Question(
        "t17", "trap",
        "Among users on mobile devices who were active in February 2025, what percent made "
        "a purchase in February 2025?",
        "percent",
        f"""SELECT 100.0 * COUNT(DISTINCT CASE WHEN e.event_name = 'purchase'
                                               THEN e.user_id END)
                  / COUNT(DISTINCT e.user_id)
           FROM g_events e JOIN g_users u USING (user_id)
           WHERE u.device = 'mobile' AND e.biz_date {FEB}""",
        f"""SELECT 100.0 * COUNT(DISTINCT CASE WHEN e.event_name = 'purchase'
                                               THEN e.user_id END)
                  / COUNT(DISTINCT e.user_id)
           FROM events e JOIN users u USING (user_id)
           WHERE u.device = 'mobile' AND e.{FEB_UTC}""",
    ),
    Question(
        "t18", "trap", "What was the largest single order in the data, in US dollars (gross)?",
        "usd",
        "SELECT MAX(gross_cents) / 100.0 FROM g_orders",
        "SELECT MAX(revenue_cents) FROM events WHERE event_name = 'purchase'",
        ("units",),
    ),
    Question(
        "t19", "trap", "How many daily active users were there on the most recent complete day?",
        "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date = DATE '2025-03-30'",
        "SELECT COUNT(DISTINCT user_id) FROM events "
        "WHERE CAST(event_ts AS DATE) = (SELECT MAX(CAST(event_ts AS DATE)) FROM events)",
        ("partial_period",),
    ),
    # ---- ambiguous wording: the definitions decide -------------------------------------
    Question(
        "a01", "ambiguous", "How many active users did we have in February 2025?", "count",
        f"SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date {FEB}",
        f"SELECT COUNT(DISTINCT user_id) FROM events WHERE {FEB_UTC}",
        ("definition",),
    ),
    Question(
        "a02", "ambiguous", "What was our conversion rate in February 2025?", "percent",
        f"""SELECT 100.0 * COUNT(DISTINCT CASE WHEN event_name = 'purchase' THEN user_id END)
                 / COUNT(DISTINCT user_id)
           FROM g_events WHERE biz_date {FEB}""",
        f"""SELECT 100.0 * COUNT(*) FILTER (WHERE event_name = 'purchase')
                 / COUNT(*) FILTER (WHERE event_name = 'view_product')
           FROM events WHERE {FEB_UTC}""",
        ("definition",),
    ),
    Question(
        "a03", "ambiguous", "What was revenue in January 2025?", "usd",
        f"SELECT SUM(net_cents) / 100.0 FROM g_orders WHERE order_date {JAN}",
        f"SELECT SUM(revenue_cents) / 100.0 FROM events "
        f"WHERE event_name = 'purchase' AND {JAN_UTC}",
        ("definition", "refunds"),
    ),
    Question(
        "a04", "ambiguous", "How many customers do we have?", "count",
        "SELECT COUNT(DISTINCT user_id) FROM g_orders WHERE net_cents > 0",
        "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_name = 'purchase'",
        ("definition", "refunds"),
    ),
    Question(
        "a05", "ambiguous", "What was the refund rate in February 2025?", "percent",
        f"SELECT 100.0 * SUM(refund_cents) / SUM(gross_cents) FROM g_orders "
        f"WHERE order_date {FEB}",
        f"""SELECT 100.0 * (SELECT COUNT(*) FROM refunds
                            WHERE refund_ts >= TIMESTAMP '2025-02-01'
                              AND refund_ts < TIMESTAMP '2025-03-01')
                 / (SELECT COUNT(*) FROM events WHERE event_name = 'purchase' AND {FEB_UTC})""",
        ("definition", "refunds"),
    ),
    Question(
        "a06", "ambiguous", "How many orders did we get last week?", "count",
        "SELECT COUNT(*) FROM g_orders "
        "WHERE order_date BETWEEN DATE '2025-03-24' AND DATE '2025-03-30'",
        "SELECT COUNT(*) FROM events WHERE event_name = 'purchase' "
        "AND event_ts >= (SELECT MAX(event_ts) FROM events) - INTERVAL 7 DAY",
        ("definition", "partial_period"),
    ),
    Question(
        "a07", "ambiguous", "What was ARPU in February 2025, in US dollars?", "usd",
        f"""SELECT (SELECT SUM(net_cents) FROM g_orders WHERE order_date {FEB}) / 100.0
                 / (SELECT COUNT(DISTINCT user_id) FROM g_events WHERE biz_date {FEB})""",
        f"""SELECT (SELECT SUM(revenue_cents) FROM events
                    WHERE event_name = 'purchase' AND {FEB_UTC}) / 100.0
                 / (SELECT COUNT(*) FROM users)""",
        ("definition", "refunds"),
    ),
    Question(
        "a08", "ambiguous",
        "What is the retention rate of users who signed up the week of Monday 2025-01-13?",
        "percent",
        """WITH cohort AS (SELECT user_id FROM g_users
                          WHERE signup_date BETWEEN DATE '2025-01-13' AND DATE '2025-01-19'),
                active AS (SELECT DISTINCT user_id FROM g_events
                           WHERE biz_date BETWEEN DATE '2025-01-20' AND DATE '2025-01-26')
           SELECT 100.0 * COUNT(a.user_id) / COUNT(*)
           FROM cohort c LEFT JOIN active a USING (user_id)""",
        """WITH cohort AS (SELECT user_id FROM users
                          WHERE signup_date BETWEEN DATE '2025-01-13' AND DATE '2025-01-19')
           SELECT 100.0 * COUNT(DISTINCT e.user_id) / (SELECT COUNT(*) FROM cohort)
           FROM events e JOIN cohort c USING (user_id)
           WHERE e.event_ts >= TIMESTAMP '2025-01-20'""",
        ("definition",),
    ),
    # ---- unanswerable: abstaining is correct ---------------------------------------------
    Question(
        "u01", "unanswerable", "What was net revenue in April 2025, in US dollars?", "usd", None,
        "SELECT COALESCE(SUM(revenue_cents), 0) / 100.0 FROM events WHERE event_name = "
        "'purchase' AND event_ts >= TIMESTAMP '2025-04-01'",
        ("partial_period",),
    ),
    Question(
        "u02", "unanswerable",
        "What was the purchase conversion rate for users acquired through paid search in "
        "February 2025?",
        "percent", None, None, ("not_instrumented",),
    ),
    Question(
        "u03", "unanswerable", "What was gross margin in February 2025, as a percent?",
        "percent", None, None, ("not_instrumented",),
    ),
    Question(
        "u04", "unanswerable", "How many sessions did we have in February 2025?", "count", None,
        f"""WITH e AS (
                SELECT user_id, event_ts,
                       LAG(event_ts) OVER (PARTITION BY user_id ORDER BY event_ts) AS prev_ts
                FROM events WHERE {FEB_UTC})
           SELECT COUNT(*) FROM e
           WHERE prev_ts IS NULL OR event_ts - prev_ts > INTERVAL 30 MINUTE""",
        ("not_instrumented",),
    ),
    Question(
        "u05", "unanswerable", "How many daily active users were there on 2025-03-31?", "count",
        None,
        "SELECT COUNT(DISTINCT user_id) FROM events "
        "WHERE CAST(event_ts AS DATE) = DATE '2025-03-31'",
        ("partial_period",),
    ),
    Question(
        "u06", "unanswerable", "What is the median age of our purchasers?", None, None, None,
        ("not_instrumented",),
    ),
]

QUESTIONS_BY_ID = {q.id: q for q in QUESTIONS}

# Holdout set, fixed before any holdout run: exactly the questions whose holdout gold moves
# when only the undocumented re-submitted-orders rule is switched off (tests check this). t13
# also changes on the holdout warehouse -- a re-submission is a distinct purchase event -- but
# whether that is a "user action" is ambiguous, so it is not part of the holdout set.
HOLDOUT_QUESTION_IDS = ("t01", "t02", "t03", "t04", "t05", "t15", "a03", "a05", "a06", "a07")
HOLDOUT_QUESTIONS = [QUESTIONS_BY_ID[q] for q in HOLDOUT_QUESTION_IDS]
