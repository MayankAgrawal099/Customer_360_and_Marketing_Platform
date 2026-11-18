"""Draws docs/architecture/architecture.svg (and the PNG, when rsvg-convert is installed).

    python docs/architecture/build_diagram.py

Standard library only. The names in the boxes are checked against the repository by tests/test_architecture.py, so the picture
cannot drift from the code.
"""

from __future__ import annotations

import shutil
import subprocess
from html import escape
from pathlib import Path

HERE = Path(__file__).parent
W, H = 2000, 1335

NAVY, GREEN, ORANGE, BLUE, LIGHT, GREY, INK, MUTE = "#0F2A43", "#0B6E4F", "#E07A1F", "#2F5D9B", "#5B9BD5", "#5A6573", "#1B2733", "#5A6573"
FONT = "DejaVu Sans, Verdana, Arial, sans-serif"
MONO = "DejaVu Sans Mono, Consolas, Menlo, monospace"

# ------------------------------------------------------------------ the content (names are verified by a test)
SOURCES_REAL = ["bigquery-public-data.ga4_obfuscated_sample_ecommerce", "Google Merchandise Store", "2020-11-01 to 2021-01-31, about 4.3 million events"]
SOURCES_SYN = ["CRM customers", "CRM orders (web orders reuse real GA4 purchases)", "Ad spend (assumed cost per click)",
               "Segment identify and track events", "Identity ground truth (scoring only)"]
RAW_TABLES = [("ga4_events", GREEN), ("crm_customers", ORANGE), ("crm_orders", ORANGE), ("ad_spend", ORANGE),
              ("segment_identifies", ORANGE), ("segment_tracks", ORANGE), ("ground_truth_identity_links  (scoring only)", ORANGE)]
IDENTITY_TABLES = ["identity_links  (device to customer)", "identity_rejected  (evidence not used)"]
STAGING = ["stg_ga4__events", "stg_ga4__purchases", "stg_crm__customers", "stg_crm__orders", "stg_ad_spend",
           "stg_segment__identifies", "stg_segment__tracks", "stg_identity__links"]
INTERMEDIATE = ["int_ga4__sessions", "int_conversion_touchpoints"]
MARTS_CORE = ["fct_sessions", "fct_orders", "dim_customers"]
MARTS_SCORING = ["fct_customer_rfm", "fct_customer_clv", "dim_customer_segments", "fct_customer_segments"]
MARTS_ATTRIBUTION = ["fct_attribution_journeys", "fct_attribution_credits", "fct_attribution_by_channel",
                     "fct_attribution_model_comparison", "fct_attribution_checks"]
MARTS_RETURN = ["fct_campaign_roi", "fct_channel_roi", "fct_campaign_cpa", "fct_channel_cpa"]
PY_COMMANDS = ["src.load_to_bigquery", "src.identity.run", "src.export_for_tableau"]

out: list[str] = []


def add(s: str) -> None:
    out.append(s)


def text(x, y, s, size=13, fill=INK, weight="normal", family=FONT, anchor="start"):
    add(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def band(y, h, label):
    add(f'<rect x="30" y="{y}" width="{W - 60}" height="{h}" rx="14" fill="#F5F7FA" stroke="#E3E8EF"/>')
    text(W - 50, y + 28, label, 15, NAVY, "bold", FONT, "end")


def box(x, y, w, title, lines, head=NAVY, mono=False, line_h=22, colors=None, sub=None):
    """A white card with a coloured header. Returns (x, y, w, h)."""
    h = 36 + len(lines) * line_h + 16 + (18 if sub else 0)
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="white" stroke="#D5DCE6"/>')
    add(f'<path d="M{x} {y + 36} V{y + 8} a8 8 0 0 1 8 -8 H{x + w - 8} a8 8 0 0 1 8 8 V{y + 36} Z" fill="{head}"/>')
    text(x + 12, y + 24, title, 14, "white", "bold")
    yy = y + 36 + 22
    if sub:
        text(x + 12, yy, sub, 12, MUTE)
        yy += 18
    for i, line in enumerate(lines):
        colour = colors[i] if colors else INK
        text(x + 12, yy + i * line_h, line, 13, colour, "bold" if colors else "normal", MONO if mono else FONT)
    return x, y, w, h


def command(x, y, w, name, note):
    h = 62
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#EEF1F5" stroke="#9AA5B1"/>')
    text(x + 12, y + 26, name, 13, INK, "bold", MONO)
    text(x + 12, y + 47, note, 12, MUTE)
    return x, y, w, h


def arrow(points, dashed=False, colour=GREY, label=None, label_at=None):
    d = "M" + " L".join(f"{px} {py}" for px, py in points)
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    add(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="2"{dash} marker-end="url(#arrow-{colour[1:]})"/>')
    if label:
        lx, ly = label_at
        text(lx, ly, label, 12, colour, "normal", FONT, "middle")


# ------------------------------------------------------------------ canvas
add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
    f'aria-label="Architecture of the Customer 360 and Marketing Attribution Platform">')
add("<defs>")
for c in (GREY, ORANGE):
    add(f'<marker id="arrow-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>')
add("</defs>")
add(f'<rect width="{W}" height="{H}" fill="white"/>')
text(40, 42, "Customer 360 and Marketing Attribution Platform: architecture", 24, NAVY, "bold")
text(40, 66, "How real GA4 data and synthetic CRM, order and ad-spend data become customer segments, attribution, campaign return and budget recommendations", 13, MUTE)

lx = 1380
text(lx, 30, "Legend", 12, NAVY, "bold")
for i, (c, label) in enumerate([(GREEN, "Real data"), (ORANGE, "Synthetic data"), (BLUE, "BigQuery dataset"), (LIGHT, "dbt views"), (NAVY, "dbt tables"), ("#9AA5B1", "Python command")]):
    cx = lx + (i % 3) * 190
    cy = 44 + (i // 3) * 22
    add(f'<rect x="{cx}" y="{cy}" width="14" height="14" rx="3" fill="{c}"/>')
    text(cx + 22, cy + 12, label, 12, INK)

# ------------------------------------------------------------------ band 1: sources
band(90, 220, "1  SOURCES")
ga4 = box(60, 125, 640, "GA4 sample e-commerce  (REAL)", SOURCES_REAL, GREEN)
syn = box(800, 125, 600, "Synthetic data  (Faker, fixed seed 42)", SOURCES_SYN, ORANGE)
arrow([(700, 185), (800, 185)], dashed=True, colour=ORANGE)
text(750, 168, "sized from", 12, ORANGE, anchor="middle")
text(750, 207, "real data", 12, ORANGE, anchor="middle")

# ------------------------------------------------------------------ band 2: load and identity
band(335, 270, "2  LOAD AND IDENTITY  (Python and BigQuery)")
load = command(60, 445, 230, "src.load_to_bigquery", "copy and load")
raw = box(350, 375, 340, "BigQuery dataset  raw", [t for t, _ in RAW_TABLES], BLUE, colors=[c for _, c in RAW_TABLES], mono=True, line_h=21)
idrun = command(780, 445, 320, "src.identity.run", "rules: identify_verified, order_match")
idt = box(1180, 428, 350, "BigQuery dataset  identity", IDENTITY_TABLES, BLUE)

arrow([(175, ga4[1] + ga4[3]), (175, 445)])                            # GA4 -> load
arrow([(1100, syn[1] + syn[3]), (1100, 322), (255, 322), (255, 445)])  # synthetic -> load
arrow([(290, 476), (350, 476)])                                        # load -> raw
arrow([(690, 476), (780, 476)])
text(735, 464, "evidence", 12, MUTE, anchor="middle")
arrow([(1100, 476), (1180, 476)])

# ------------------------------------------------------------------ band 3: dbt
band(650, 375, "3  DBT MODELS  (BigQuery: staging, intermediate and marts)")
stg = box(60, 695, 250, "staging  (views)", STAGING, LIGHT, mono=True, line_h=21)
inter = box(375, 695, 290, "intermediate  (views)", INTERMEDIATE, LIGHT, mono=True)
core = box(730, 695, 230, "marts: core", MARTS_CORE, NAVY, mono=True)
attr = box(1025, 695, 340, "marts: attribution", MARTS_ATTRIBUTION, NAVY, mono=True)
roi = box(1430, 695, 290, "marts: campaign return", MARTS_RETURN, NAVY, mono=True, sub="also reads stg_ad_spend")
scoring = box(700, core[1] + core[3] + 40, 290, "marts: customer scoring", MARTS_SCORING, NAVY, mono=True)

arrow([(520, raw[1] + raw[3]), (520, 616), (185, 616), (185, 695)])      # raw -> staging
text(352, 608, "source()", 12, MUTE, anchor="middle")
arrow([(1355, idt[1] + idt[3]), (1355, 632), (240, 632), (240, 695)])    # identity -> staging
text(800, 624, "source()", 12, MUTE, anchor="middle")
arrow([(310, 750), (375, 750)])
arrow([(665, 750), (730, 750)])
arrow([(960, 750), (1025, 750)])
arrow([(1365, 750), (1430, 750)])
arrow([(845, core[1] + core[3]), (845, scoring[1])])

# ------------------------------------------------------------------ band 4: outputs and checks
band(1050, 250, "4  OUTPUTS AND CHECKS")
export = command(760, 1120, 520, "src.export_for_tableau", "7 CSV files, no personal fields; budget rules applied here")
tab = box(1350, 1120, 330, "Tableau Public dashboards", ["Customer 360 and Segments", "Attribution, ROI and CPA", "(with budget recommendations)"], GREEN)
reports = box(1710, 1120, 240, "Reports  (Markdown)", ["identity accuracy", "attribution comparison", "dbt test results"], GREY)
checks = box(60, 1120, 640, "Quality checks at every step",
             ["dbt tests: generic tests on every model plus 30 singular tests",
              "Identity scored against the ground truth (precision, recall)",
              "Attribution: 30 checks that every model credits the same revenue",
              "pytest: real model SQL run on small tables in DuckDB"], "#B7791F")

arrow([(845, scoring[1] + scoring[3]), (845, 1120)])
arrow([(1100, attr[1] + attr[3]), (1100, 1120)])
arrow([(1575, roi[1] + roi[3]), (1575, 1090), (1250, 1090), (1250, 1120)])
arrow([(1280, 1151), (1350, 1151)])

add("</svg>")

svg = "\n".join(out)
(HERE / "architecture.svg").write_text(svg, encoding="utf-8")
print("wrote", HERE / "architecture.svg")

rsvg = shutil.which("rsvg-convert")
if rsvg:
    subprocess.run([rsvg, "-w", "2400", "-b", "white", str(HERE / "architecture.svg"), "-o", str(HERE / "architecture.png")], check=True)
    print("wrote", HERE / "architecture.png")
else:
    print("rsvg-convert not found: the SVG is written, the PNG was not refreshed")
