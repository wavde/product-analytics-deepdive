# Known data traps

Things in this warehouse that make a reasonable-looking query return a wrong number.
Each entry says what goes wrong, how big it tends to be, and the check that catches it.
Kept separate from the definitions on purpose: definitions say what a metric *means*;
this file says where the data will mislead you while you compute it.

## Duplicate events from client retries

The mobile and web clients retry a send when they don't get an acknowledgement, so about
4% of user-initiated events arrive twice: same `event_id`, same `order_id`, later
`ingested_at`. `COUNT(*)` and `SUM(revenue_cents)` over raw `events` overstate orders and
revenue by roughly that much. `COUNT(DISTINCT user_id)` is unaffected.

*Check:* `COUNT(*)` vs `COUNT(DISTINCT event_id)` on the rows you are aggregating.

## QA accounts placing real-looking orders

Ten internal accounts (`is_internal = true`) run checkout tests every weekday, roughly
two orders each per day at normal prices. They add about 14 orders for every 100 real
ones on weekdays, and they also show up as active users and purchasers.

*Check:* join to `users` and confirm the filter on `is_internal` is in every CTE that
counts users or money, including denominators.

## Messaging events in the events table

`email_delivered` (Tuesdays, sent to every signed-up user) and `push_delivered`
(Thursday evenings Pacific, to a sample of mobile users) sit in `events` beside real
activity. Counting distinct users over all event names turns a Tuesday's DAU into
"everyone who has an inbox", and makes every signup cohort look 100% retained.

*Check:* if DAU jumps on Tuesdays or retention is near 100%, look at which `event_name`
values you included.

## UTC timestamps, Pacific reporting

`event_ts` is UTC. `CAST(event_ts AS DATE)` gives the UTC date, which puts everything
after 16:00 Pacific (17:00 during daylight time) on the next day. Daily numbers shift by
a third of a day; monthly totals move at the boundaries. Daylight saving starts
2025-03-09, so a fixed `- INTERVAL 8 HOUR` is wrong for most of March.

*Check:* convert with `event_ts AT TIME ZONE 'UTC' AT TIME ZONE 'America/Los_Angeles'`
before casting to a date, and spot-check one known timestamp either side of 2025-03-09.

## Refunds live elsewhere and arrive late

Refunds are in their own table, issued 1-21 days after the order. Summing
`refund_cents` by `refund_ts` month mixes refunds on last month's orders into this
month and understates refunds on recent orders. Recent periods' net revenue keeps
falling for three weeks after they close. Refund *rate* by count is a different (and
smaller) number than refund rate by dollars, because partial refunds exist.

*Check:* join refunds to orders on `order_id` and group by the order's business date.

## The final day is partial

The load stops at `etl_watermark.loaded_through` (2025-03-31 18:00 UTC, which is 11:00
on 2025-03-31 in Los Angeles). `MAX(event_ts)` therefore lands on a half-loaded day.
"Latest day" or "last 7 days" anchored on `MAX(event_ts)` reports a partial period that
looks like a sudden drop.

*Check:* read `etl_watermark` first and anchor relative periods on the last complete
business day.

## Money is in cents

`revenue_cents` and `refund_cents` are integers in cents. Forgetting the `/ 100.0`
inflates dollar figures 100x; integer division truncates.

*Check:* a typical order is around $30; if yours is $3,000, you forgot to divide.

## Things that look answerable but aren't

There is no session id, no acquisition channel, no cost data and no age. Sessionising
events with a 30-minute gap, or treating `country` as a channel, produces a number with
no agreed meaning. Say the data doesn't support the question.
