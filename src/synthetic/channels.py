"""Channel grouping and the cost assumptions for paid channels.

``channel_group`` turns a session's source and medium into one channel name. The dbt models use
the same rules, so keep the two in step.

Sessions with no source information at all are "Unassigned": the GA4 sample leaves the source
parameters empty on many sessions, and guessing a channel for them would invent attribution.
"""

# (low, high) ranges; each campaign gets one value drawn from the range, then daily noise.
# Affiliate cost stands for commission per click; Email cost stands for platform and send cost per click.
PAID_CHANNELS = {
    "Paid Search": {"cpc": (0.55, 1.25), "ctr": (0.020, 0.050)},
    "Display": {"cpc": (0.15, 0.45), "ctr": (0.003, 0.008)},
    "Paid Social": {"cpc": (0.30, 0.80), "ctr": (0.008, 0.020)},
    "Affiliate": {"cpc": (0.10, 0.30), "ctr": (0.010, 0.030)},
    "Email": {"cpc": (0.02, 0.08), "ctr": (0.020, 0.060)},
}

SOCIAL_SOURCES = ("facebook", "instagram", "twitter", "t.co", "linkedin", "pinterest", "reddit")
DISPLAY_SOURCES = ("googleads.g.doubleclick.net", "doubleclick.net")


def _text(value) -> str:
    """Lower-case text, treating None and NaN (an empty CSV cell read by pandas) as empty."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value).strip().lower()


def channel_group(source, medium) -> str:
    s, m = _text(source), _text(medium)
    if not s and not m:
        return "Unassigned"
    if m in ("cpc", "ppc", "paidsearch", "paid search"):
        return "Paid Search"
    if m in ("cpm", "display", "banner") or any(d in s for d in DISPLAY_SOURCES):
        return "Display"
    if m in ("paid_social", "paidsocial", "paid social", "social_paid"):
        return "Paid Social"
    if m == "organic":
        return "Organic Search"
    if m == "email":
        return "Email"
    if m == "affiliate":
        return "Affiliate"
    if m in ("social", "organic_social", "social_organic") or (m == "referral" and any(x in s for x in SOCIAL_SOURCES)):
        return "Organic Social"
    if m == "referral":
        return "Referral"
    if m in ("(none)", "none") or s in ("(direct)", "direct"):
        return "Direct"
    return "Other"
