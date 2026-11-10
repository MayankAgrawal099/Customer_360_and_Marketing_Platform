"""Every assumption used to build the synthetic CRM, orders, ad-spend and Segment-style data.

One place, so the README and docs/synthetic_data.md can quote the exact numbers.
Changing any value changes the output; the seed makes each run repeatable.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    seed: int = 42

    # Who becomes a CRM customer
    guest_checkout_rate: float = 0.12        # share of GA4 buyers who check out as guests (not in the CRM)
    nonbuyer_signup_rate: float = 0.01       # share of GA4 non-buyers who register (newsletter, account)
    existing_customer_rate: float = 0.20     # share of buyers whose account predates the GA4 window
    multi_device_rate: float = 0.08          # share of customers who also use a second device

    # How well identity signals are captured (these decide the best possible match accuracy)
    identify_capture_rate: float = 0.85      # Segment identify fired on the customer's main device
    second_device_capture_rate: float = 0.70 # ... and on the second device
    txn_id_match_rate: float = 0.92          # CRM web orders that carry the GA4 transaction_id

    # Orders
    app_orders_mean: float = 0.20            # extra app orders per customer (Poisson mean), not seen by GA4 web
    refund_rate: float = 0.03                # share of orders refunded in full

    # CRM details
    marketing_opt_in_rate: float = 0.55

    # Ad spend (clicks are a little above sessions because some clicks never become a session)
    click_per_session_low: float = 1.00
    click_per_session_high: float = 1.15
    daily_noise_sigma: float = 0.10
