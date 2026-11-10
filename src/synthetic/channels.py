"""Channel grouping and the cost assumptions for paid channels.

``channel_group`` turns GA4's source and medium into one channel name. The dbt models use
the same rules, so keep the two in step.
"""

# (low, high) ranges; each campaign gets one value drawn from the range, then daily noise.
PAID_CHANNELS = {
    "Paid Search": {"cpc": (0.55, 1.25), "ctr": (0.020, 0.050)},
    "Display": {"cpc": (0.15, 0.45), "ctr": (0.003, 0.008)},
    "Paid Social": {"cpc": (0.30, 0.80), "ctr": (0.008, 0.020)},
}


def channel_group(source, medium) -> str:
    s = (source or "").strip().lower()
    m = (medium or "").strip().lower()
    if m in ("cpc", "ppc", "paidsearch", "paid search"):
        return "Paid Search"
    if m in ("cpm", "display", "banner"):
        return "Display"
    if m in ("paid_social", "paidsocial", "paid social", "social_paid"):
        return "Paid Social"
    if m == "organic":
        return "Organic Search"
    if m == "referral":
        return "Referral"
    if m == "email":
        return "Email"
    if m == "affiliate":
        return "Affiliate"
    if m in ("social", "organic_social", "social_organic"):
        return "Organic Social"
    if m in ("(none)", "none", "") or s in ("(direct)", "direct"):
        return "Direct"
    return "Other"
