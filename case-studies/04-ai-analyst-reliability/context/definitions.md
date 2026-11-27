# Metric definitions

These are the team's agreed definitions. When a question uses one of these terms, this
is what it means, even if another reading is plausible. If a question can't be answered
under these definitions, say so rather than inventing a new one.

## Ground rules (apply to every metric)

1. **Reporting time zone is `America/Los_Angeles`.** Days, weeks and months are business
   periods in that zone, including the daylight-saving change on 2025-03-09. `event_ts`
   and `refund_ts` are UTC and must be converted before bucketing. `signup_date` is
   already a business date.
2. **Weeks run Monday to Sunday.**
3. **Internal accounts never count.** Exclude `users.is_internal = true` from every user,
   order, revenue and rate metric, in numerators and denominators.
4. **One logical event per `event_id`.** If an `event_id` appears more than once, keep one
   row.
5. **Only user-initiated events count as activity:** `view_product`, `add_to_cart`,
   `checkout`, `purchase`. Messaging events (`*_delivered`) are things we did *to* the
   user and never make anyone active.
6. **Only report complete periods.** Data is complete up to `etl_watermark.loaded_through`.
   A business day, week or month that ends after the watermark is incomplete and is not
   reported. Relative periods ("yesterday", "last week", "latest") mean the most recent
   *complete* period.
7. **Money is reported in US dollars**, from cents divided by 100.

## Users and activity

| Term | Definition |
|---|---|
| Active user (period P) | Distinct user with at least one user-initiated event in P. |
| DAU / WAU / MAU | Active users for a business day / Monday-Sunday week / calendar month. "Active users" with a month named means MAU. |
| Purchaser (P) | Distinct user with at least one order in P. |
| Customer | User with at least one order that is not fully refunded, as of the watermark. "How many customers" means all-time to date. |
| Week-1 retention (cohort W) | Of users whose `signup_date` falls in week W, the percent active in week W+1. "Retention" without a horizon means week-1 retention. |
| WPAU (day D) | Distinct purchasers in the 7 business days ending on D, inclusive. |

## Orders and money

| Term | Definition |
|---|---|
| Order | One deduplicated `purchase` event, identified by `order_id`. Order date = business date of the purchase. |
| Gross revenue (P) | Sum of order amounts for orders dated in P. |
| Refunds (P) | Refunds on orders dated in P, **attributed to the order date, not the refund date.** |
| Net revenue (P) | Gross revenue minus refunds, both by order date. "Revenue" without a qualifier means net revenue. |
| Refund rate (P) | Refunded dollars / gross dollars for orders dated in P, as a percent. Not a count ratio. |
| Average order value (P) | Gross revenue / orders. |
| ARPU (P) | Net revenue / active users in P. |
| Conversion rate (P) | Purchasers / active users in P, as a percent. "Conversion" without a qualifier means this user-level rate, not orders per view. |

## Not instrumented

We do not track sessions, acquisition channel or campaign, product cost or margin, or
user demographics such as age. Don't approximate them from other columns: say the
question can't be answered from this data.
