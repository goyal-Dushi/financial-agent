

### Variouse schemas 

- `requests.csv`: contains current financial questions from the users.
    - Schema
        - `request_id`: format is "request_<id>", unique
        - `user_id` : format is "user_<id>", id of user making the request
        - `request_date`: format is YYYY-MM-DD, date on which the request is evaluated
        - `request_type`: category of financial request. Its one of:
            1. purchase
            2. travel
            3. education
            4. family_transfer
            5. debt_repayment
            6. investment
            7. housing
            8. emergency_expense
            9. other
        - `requested_amount`: total amount the user wants to commit, float
        - `desired_completion_date`: date by which the user wants to complete the request
        - `allows_partial_payment`: whether the request permits paying part today and the remaining balance later, boolean ( true / false)
        - `request_text`: the user’s question or instruction 

<!-- - `sample_requests.csv` contains public examples with completed output fields. Use it to understand format and decision style, not as labels for evaluation requests. -->
- `financial_profiles.csv` defines the user's home currency, current available balance, minimum balance to keep, priorities, protected spending, adjustable categories, and payment preferences. 
    - Schema
        1. `user_id`: id of the user whose financial profile data is present
        2. `home_currency`: The dataset includes INR, ZAR, IDR, USD, and EUR. The native currency in which user trades in.
        3. `current_available_balance`: current bank balance of the user, float value
        4. `minimum_balance_to_keep`: the minimum bank balance that should be always maintained at all cost
        5. `financial_priorities`: the financial priorities of the user, Below are the possible types: 
            - debt_repayment
            - emergency_savings
            - retirement_investment
            - healthcare
            - housing
            - family_support
            - travel
            - education
        these are separated by "|" to justify multiple financial priorities by a user.
        6. `expense_categories_to_protect`: the various  daily life activities where user want to spend his money on and cannot reduce them, these expenses are not under his control and required for the user to fullfill. These include :
            - transport
            - rent
            - groceries
            - debt_repayment
            - housing
            - family_support
            - education
            - insurance
            - utilities
            - healthcare
        It will be different for differnet users, and are separated by "|" for multiple such items.
        7. `expense_categories_user_is_willing_to_reduce`: as name suggests, these are unnecessary expenses which user can reduce. These include:
            - entertainment
            - streaming
            - dining
            - gym
            - shopping
        8. `payment_methods_user_will_consider`: these are the payment methods user can consider when making payments for the requested_amount in requests table.These include: 
            - partial_payment
            - full_payment
            - installments
        9. `max_installment_months`: these will be empty in case if user prefers to pay in full (full_payment is only value in payment_methods_user_will_consider). But, for rest of other payment methods, this specifies, in how many time (in months), user is willing to pay the requested_amount , either as partial payment or in installments
`max_installment_months` is blank when the user will not consider installments.
- `financial_events.csv` contains historical, pending, scheduled, settled, failed, cancelled, and non-cash records of the users
    - Schema
        1. `event_id`: unqiue identifier for each event in the table ( format "event_<id>" )
        2. `user_id`: id to link user to each of the events
        3. `event_type`: this describes the type of event, it can be of below types: 
            - investment_purchase
            - subscription
            - expense
            - income
            - investment_valuation
            - refund
            - investment_sale
            - debt_payment
        4. `description`: descibes each of the event type, what it is meant for
        5. `category`: for which purpose the user is having this event for , it is mainly of below types: 
            - debt_repayment
            - work_expense
            - housing
            - music_subscription
            - salary
            - streaming
            - transport
            - dining
            - cloud_storage
            - investment
            - rent
        6. `direction`: it states whether the money is spend or came back to user account, or didn't involve any transaction at all 
            - debit
            - credit
            - non_cash : its usually where we are just valuating the portfolio of a particular user, or their investment valuation
        7. `amount`: the amount of money involved in that event
        8. `currency`: the type of currency the event transaction was dealt in
        9. `event_date`: when the event occurred
        10. `settlement_date`: if the event involved any payment of dues , then, when were they settled
        11. `status`: its descibes the current status of the event. It can be of type as follows: 
            - pending
            - cancelled
            - unrealized
            - failed
            - settled
            - scheduled
        12. `flexibility`
        13. `minimum_allowed_amount`
        14. `linked_event_id`: points to an earlier event in the same transaction or investment lifecycle; the link alone does not determine whether a row counts toward cash flow. Treat `settled`, `pending`, `scheduled`, and `unrealized` according to their cash state; do not treat unrealized investment value as available cash.
- `exchange_rates.csv` supplies fixed rates. For a foreign-currency cash event, use the row for its settlement date and the stated `from_currency` to `to_currency` direction.
    - Schema
        1. `rate_date`: the date of exchange rate
        2. `from_currency`
        3. `to_currency`
        4. `rate`
- `request_payment_options.csv` contains the seller/provider payment options available for a request. A request has two to four options. An available option may still be rejected because it conflicts with the user's payment preferences or `max_installment_months`.
    - Schema
        1. `payment_option_id`: id to uniquely identify each payment option
        2. `request_id`: a request_id associated with requests table, where each request may or may not have multiple payment options associated
        3. `payment_method`: method of payment associated with the option. Its mainly of below types: 
            - full_payment
            - installments
        4. `payment_amount`: based on payment method, what's the amount of payment that needs to be made. In case of installements, it includes only the single installment amount, adding the financing fee per installement as well. 
        5. `number_of_payments`: if not full payment, then, in how many installements the user can fully pay the amount
        6. `first_payment_date`: starting date of the payment option for the request
        7. `payment_frequency_days`: recurring frequency of each installment cycle, starting from the first_payment_date
        8. `financing_fee`: the total financing fee across all installments
        9. `total_payable_amount`: (payment_amount*number_of_payments) or requested_amount+financing_fee, where requested_amount is from the requests table
- `messages.csv`: provide optional supporting evidence. The `related_event_id` is populated only when the message directly describes one supplied financial-event row; a blank value means no one-to-one event row exists.
    - Schema
        1. `message_id`: unique identifier for each message, format (message<id> )
        2. `user_id`: id of the user 
        3. `request_id`:
        4. `related_event_id`
        4. `sent_at`: date of the message when it was send
        5. `source_type`: who send the message
        6. `message_text`
- `images.csv`: provide optional supporting evidence. Resolve each image as `dataset/media/images/<image_id>.png`; for example, `image_07` maps to `dataset/media/images/image_07.png`. Use the information only when relevant; we do not invent evidence when an image file is absent.


### Output csv to be generated
- Schema
    1. `amount_safe_to_pay`: largest amount the user can safely pay on `request_date` before optional spending changes, while covering protected expenses and maintaining their minimum balance
    2. `affordability_status`: whether the request is affordable now, affordable with a plan, affordable later, or not affordable
        - `affordable_now`: the full amount is safe to pay on `request_date` and the user accepts `full_payment`
        - `affordable_with_plan`: the full requested amount can be completed safely using a partial-payment schedule, installments, or permitted spending changes
        - `affordable_later`: the full amount is expected to become safe later
        - `not_affordable`: the full request cannot be completed safely within the forecast period
    3. `recommended_payment_method`: the safest recommended payment approach
        - `full_payment`
        - `partial_payment`
        - `installments`
        - `wait`
        - `not_recommended`
    4. `payment_plan`: all payments in the recommendation
    5. `earliest_date_for_full_payment`: earliest date when the full amount is forecast to be safe as a single payment. measures financial capacity independently of the user's payment-method preferences. It may equal `request_date` even when the selected recommendation is installments because the user has chosen not to consider full payment.
    6. `spending_changes_needed`: flexible expenses that must be stopped or reduced
    7. `decision_explanation`: short explanation of the recommendation and the financial facts behind it