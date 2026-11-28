# Schema: storefront analytics warehouse

DuckDB database. Four tables. This is the catalog layer: what each column *is*. It says
nothing about which rows count toward a metric; that lives in `definitions.md`.

## `users`

One row per account.

| Column | Type | Description |
|---|---|---|
| `user_id` | BIGINT | Account identifier. |
| `signup_date` | DATE | Calendar date the account was created. |
| `country` | VARCHAR | ISO-3166 alpha-2 country code at signup (`US`, `GB`, `DE`, `IN`, `BR`). |
| `device` | VARCHAR | Device type at signup: `mobile`, `desktop` or `tablet`. |
| `is_internal` | BOOLEAN | Account is operated by staff or QA automation. |

## `events`

One row per event *delivery* from the tracking pipeline.

| Column | Type | Description |
|---|---|---|
| `event_id` | VARCHAR | Identifier assigned by the client when the event happens. |
| `user_id` | BIGINT | Account the event belongs to. |
| `event_name` | VARCHAR | See values below. |
| `event_ts` | TIMESTAMP | When the event happened, in UTC (stored without a zone). |
| `ingested_at` | TIMESTAMP | When the row landed in the warehouse, in UTC. |
| `product_id` | BIGINT | Product involved; NULL for messaging events. |
| `order_id` | VARCHAR | Set on `purchase` rows only. |
| `revenue_cents` | BIGINT | Order amount in US cents on `purchase` rows; 0 otherwise. |

`event_name` values:

| Value | Meaning |
|---|---|
| `view_product` | User opened a product page. |
| `add_to_cart` | User added a product to the cart. |
| `checkout` | User started checkout. |
| `purchase` | Order placed and payment authorised. |
| `email_delivered` | Lifecycle email accepted by the recipient's mail server. |
| `push_delivered` | Push notification delivered to the device. |

## `refunds`

One row per refund transaction. An order can have at most one refund in this extract.

| Column | Type | Description |
|---|---|---|
| `refund_id` | VARCHAR | Refund identifier. |
| `order_id` | VARCHAR | Order being refunded; joins to `events.order_id`. |
| `refund_ts` | TIMESTAMP | When the refund was issued, in UTC. |
| `refund_cents` | BIGINT | Amount refunded in US cents (full or partial). |

## `etl_watermark`

| Column | Type | Description |
|---|---|---|
| `table_name` | VARCHAR | `events` or `refunds`. |
| `loaded_through` | TIMESTAMP | UTC time up to which the table is complete. |
