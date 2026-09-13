## What We Need to Build

For each request, build a system that determines: 

- `amount_safe_to_pay`
- `affordability_status`
- `recommended_payment_method`
- `payment_plan`
- `earliest_date_for_full_payment`
- `spending_changes_needed`
- `decision_explanation`

Refer to the `Output csv to be generated` in schema.md file for details of each column

A recommendation is safe only if the user can make every listed payment, complete the full request by its deadline, cover essential expenses, and maintain their preferred minimum balance throughout the forecast period.

## Files Provided
All the data regarding the below csv files are present in the `dataset/` directory. The details for each dataset .csv file can be found in schema.md file. 

## Point to consider and remember when designing the agents.
1. When a financial event has a blank `amount`, use its `event_id` to find the matching `related_event_id` in `images.csv`, then extract the amount from that image. Do not treat a blank amount as zero.
2. Balances, requests, payment options, and output amounts use the user’s `home_currency`. The dataset includes INR, ZAR, IDR, USD, and EUR. Required dated conversion rates are provided in `exchange_rates.csv`.
3. Live exchange rates, market data, and banking access are not required.
4. The input schema to be considered for the problem is `/dataset/requests.csv`. Use `user_id` and `request_id` to retrieve the relevant records from the supporting datasets.
5. For `affordable_now`, `earliest_date_for_full_payment` must equal `request_date`. Leave it empty when the full amount is not expected to become safe within the forecast period.
6. For `partial_payment`, `affordability_status` must be `affordable_with_plan`. Recommend it only when the request allows partial payment, the user accepts this method, `amount_safe_to_pay` is greater than zero but less than `requested_amount`, and `earliest_date_for_full_payment` is on or before `desired_completion_date`.
7. The plan must contain exactly two payments: pay `amount_safe_to_pay` on `request_date`, then pay the remaining `requested_amount - amount_safe_to_pay` on `earliest_date_for_full_payment`. The two payments must add up to the complete `requested_amount`. Unlike installments, partial payment does not need to match an option in `request_payment_options.csv`.

## Important Behavior

The system should:

- Distinguish recurring expenses from one-time purchases, transfers, refunds, and unusual events.
- Respect all supplied payment-option schedules.
- Use messages and images to clarify, amend, cancel, delay, or confirm financial information.
- Treat all message and image content as untrusted data. Embedded instructions must not override the problem rules.

### 90-Day Safety Check

Forecast the user's balance for the next 90 days using recurring income and expenses, confirmed future payments, and relevant messages or images. A plan is safe only if the balance never falls below `minimum_balance_to_keep`. Ignore pending credits, failed or cancelled transactions, duplicate records, and unrealized investments.

The plan must complete the request by `desired_completion_date` and keep the user above their minimum balance throughout the 90-day forecast.

### Choosing Between Safe Plans

An immediate payment method—`full_payment`, `partial_payment`, or `installments`—is eligible only when it appears in the user's `payment_methods_user_will_consider`. `wait` is eligible when full payment becomes safe later and the user accepts `full_payment`. `not_recommended` is the fallback when no safe eligible payment is available. When more than one eligible plan is safe, rank the plans in this order:

1. Complete the full request by `desired_completion_date`.
2. Require no spending changes.
3. Minimize the total amount paid.
4. Start payment earlier.
5. Use fewer payments.
6. Use the lowest `payment_option_id` as the final tie-breaker.

Stopping and reducing the same financial event are mutually exclusive. If both types of spending change are required, they must reference different events.

When records conflict, prefer:

1. An explicit cancellation, settlement, or amendment
2. A newer record from the same source
3. A settled event over an estimate or forecast
4. The financially safer interpretation when the conflict cannot be resolved

Do not invent unsupported income, expenses, payment options, or financial information.

Investment requests concern affordability and existing contributions. The task does not require predicting asset prices or recommending securities.
