"""
Style · dark editorial (NTS Radio), Balance palette.

The same grid as the reference dashboard: uppercase mono type, hard rules, no
rounded corners anywhere, cards chained without gaps. What changes is the
plane: near-black background, bone ink, and the active block goes from blue to
bone.

The categorical palette is the same eight hues as the light theme, re-stepped
for a dark surface (OKLCH L 0.48 to 0.67, at least 3:1 on the surface).
Validated with `validate_palette.js --mode dark --surface #121214`: lightness
band OK, chroma OK, contrast OK, worst adjacent pair ΔE 10.3, which is the
floor band, so anything using 4 or more series carries a legend or a direct
label and never colour alone.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# ---------------------------------------------------------------------------
# Surfaces and ink
# ---------------------------------------------------------------------------
BG = "#0a0a0b"
PANEL = "#0f0f11"
CARD = "#121214"
RULE = "#2b2b31"
RULE_SOFT = "#1e1e23"
INK = "#f1eee8"          # bone
INK_2 = "#a3a09a"
MUTED = "#6b6862"
ACCENT = "#e8e4da"       # active block (replaces the light theme blue)
GRID = "#1c1c21"

# ---------------------------------------------------------------------------
# Categorical palette (fixed order, never cycled, never follows the ranking)
# ---------------------------------------------------------------------------
CATEGORICAL = ["#3987e5", "#199e70", "#c98500", "#008300",
               "#9085e9", "#e66767", "#d55181", "#d95926"]

#: Status: reserved, never reused as "series 4".
GOOD = "#0ca30c"
WARN = "#fab219"
SERIOUS = "#ec835a"
CRITICAL = "#e5484d"

#: Colour per content category: follows the entity, not its position.
CATEGORY_COLOR = {
    "SOCIAL_MEDIA":  "#3987e5",
    "MESSAGING":     "#199e70",
    "ENTERTAINMENT": "#c98500",
    "SHOPPING":      "#008300",
    "GAMING":        "#9085e9",
    "ADULT":         "#e66767",
    "NEWS":          "#d55181",
    "GAMBLING":      "#d95926",
    "OTHER":         "#55555c",     # deliberately neutral: it is the catch-all
}

#: One colour per user, stable across the whole dashboard.
USER_COLOR = {"A": "#199e70", "B": "#d95926"}

BLOCK_TYPE_COLOR = {"APP": "#3987e5", "URL": "#c98500", "NUDITY": "#e66767"}

MONO = "IBM Plex Mono, ui-monospace, SFMono-Regular, monospace"
SANS = "Inter, sans-serif"


def register_template() -> None:
    axis = dict(
        showline=True, linecolor=RULE, linewidth=1.2, mirror=False,
        ticks="outside", tickcolor=RULE, ticklen=4,
        tickfont=dict(family=MONO, size=11, color=INK_2),
        gridcolor=GRID, zeroline=False,
        title=dict(font=dict(family=MONO, size=11, color=INK_2)),
    )
    pio.templates["balance_dark"] = go.layout.Template(
        layout=dict(
            font=dict(family=SANS, color=INK_2, size=13),
            title=dict(font=dict(family=SANS, color=INK, size=15),
                       x=0.01, xanchor="left"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            colorway=CATEGORICAL,
            xaxis=axis, yaxis=axis,
            legend=dict(bgcolor="rgba(0,0,0,0)",
                        font=dict(family=MONO, size=11, color=INK_2),
                        orientation="h", yanchor="top", y=-0.18,
                        xanchor="left", x=0),
            margin=dict(t=48, r=24, b=68, l=56),
            hoverlabel=dict(bgcolor=CARD, bordercolor=RULE,
                            font=dict(family=MONO, size=12, color=INK)),
            hovermode="x unified",
            colorscale=dict(sequential=[
                [0.0, "#10243c"], [0.25, "#17406e"], [0.5, "#1f5ca3"],
                [0.75, "#2f7ad0"], [1.0, "#5ba1ee"]]),
        )
    )
    pio.templates.default = "balance_dark"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {{
    --bg:       {BG};
    --panel:    {PANEL};
    --card:     {CARD};
    --rule:     {RULE};
    --rule-2:   {RULE_SOFT};
    --ink:      {INK};
    --ink-2:    {INK_2};
    --muted:    {MUTED};
    --accent:   {ACCENT};
    --mono: {MONO};
}}

html, body, [class*="css"], .stApp {{ font-family: {SANS} !important; }}

/* The toolbar can NOT be hidden wholesale: the button that reopens the sidebar
   lives inside it, so hiding it left the sidebar unrecoverable once collapsed.
   Only the surplus pieces are hidden (Deploy and the menu). */
[data-testid="stAppDeployButton"], [data-testid="stAppToolbarActionButton"] {{
    display: none !important;
}}
#MainMenu, footer {{ display: none !important; }}
header[data-testid="stHeader"] {{ background: transparent !important; }}

[data-testid="stExpandSidebarButton"] {{
    background: var(--accent) !important;
    border: 1.5px solid var(--rule) !important;
    color: {BG} !important;
    width: 2.1rem !important; height: 2.1rem !important;
    display: flex !important; align-items: center; justify-content: center;
    opacity: 1 !important;
}}
[data-testid="stExpandSidebarButton"] svg {{
    color: {BG} !important; fill: {BG} !important; opacity: 1 !important;
}}
[data-testid="stExpandSidebarButton"]:hover {{ background: #ffffff !important; }}

.stApp {{ background: var(--bg); color: var(--ink); }}
.block-container {{ max-width: 1560px; padding-top: 2.2rem; margin: 0 auto; }}

/* Headings: editorial, left-aligned, nothing rounded */
h1, h2, h3, h4 {{
    color: var(--ink) !important;
    letter-spacing: -0.01em;
    font-weight: 700 !important;
    text-align: left !important;
}}
h1, h2 {{
    border-bottom: 2px solid var(--rule);
    padding: 0 0 .2rem 0 !important;
    margin-bottom: .8rem;
    line-height: 1.12 !important;
}}
h3 {{
    text-transform: uppercase;
    letter-spacing: .04em;
    font-family: var(--mono) !important;
    font-size: 1.0rem !important;
    color: var(--ink) !important;
    border-left: 4px solid var(--accent);
    padding-left: 1rem !important;
    margin-top: 1.9rem !important;
    margin-bottom: .9rem !important;
}}
/* Streamlit wraps the h3 in its own container; without this the reset eats
   the padding-left and the first letter sticks to the rule again. */
[data-testid="stMarkdownContainer"] h3 {{ padding-left: 1rem !important; }}

* {{ border-radius: 0 !important; }}

section[data-testid="stSidebar"] {{
    background: var(--panel);
    border-right: 1.5px solid var(--rule);
}}
section[data-testid="stSidebar"] * {{ color: var(--ink); }}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{
    text-transform: uppercase; letter-spacing: .06em;
    font-family: var(--mono) !important;
    border-left: none; padding-left: 0;
}}
section[data-testid="stSidebar"] label {{
    text-transform: uppercase; letter-spacing: .05em;
    font-family: var(--mono) !important;
    font-size: .72rem !important; color: var(--ink-2) !important;
}}

/* Cards: hard border, flat, no shadow */
[data-testid="stMetric"],
[data-testid="stPlotlyChart"],
div[data-testid="stExpander"],
[data-testid="stDataFrame"] {{
    background: var(--card);
    border: 1.5px solid var(--rule);
    box-shadow: none !important;
    transition: border-color .12s ease;
}}
[data-testid="stMetric"] {{
    padding: .7rem .8rem; height: 6.4rem; overflow: hidden;
    position: relative; z-index: 0;
}}
[data-testid="stPlotlyChart"] {{ padding: .4rem .6rem; }}
/* The strip chains the cards by overlapping them 1.5px, so one card's right
   border sits under the next. On hover it has to be raised a layer or the
   highlight looks clipped on that side. */
[data-testid="stMetric"]:hover {{ border-color: var(--accent); z-index: 3; }}
[data-testid="stPlotlyChart"]:hover,
div[data-testid="stExpander"]:hover {{ border-color: var(--accent); }}

/* Metric row: one continuous strip, no gaps */
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {{ gap: 0 !important; }}
div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"])
    [data-testid="stColumn"]:not(:first-child) [data-testid="stMetric"] {{ margin-left: -1.5px; }}

[data-testid="stMetric"] {{
    text-align: left; display: flex; flex-direction: column; justify-content: center;
}}
[data-testid="stMetricValue"] {{
    font-family: var(--mono) !important; font-weight: 600 !important;
    font-size: 1.55rem !important; color: var(--ink) !important;
    white-space: nowrap;
}}
[data-testid="stMetricLabel"] {{
    font-family: var(--mono) !important; text-transform: uppercase;
    letter-spacing: .05em; font-size: .66rem !important; color: var(--ink-2) !important;
}}
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
    white-space: normal !important; overflow: visible !important;
    text-overflow: clip !important; line-height: 1.15 !important;
}}
[data-testid="stMetricDelta"] {{ font-family: var(--mono) !important; font-size: .72rem !important; }}

/* Tabs: uppercase mono; the active one is a solid bone block */
div[data-testid="stTabs"] [role="tablist"] {{
    display: flex; justify-content: flex-start; flex-wrap: wrap; gap: 0;
    width: 100%; border-bottom: 1.5px solid var(--rule);
}}
/* Streamlit renamed the tab from <button> to div[data-testid="stTab"] in 1.5x;
   both are targeted so the styling does not depend on the version. */
div[data-testid="stTabs"] button,
div[data-testid="stTabs"] [data-testid="stTab"] {{
    color: var(--ink-2) !important; font-family: var(--mono) !important;
    text-transform: uppercase; letter-spacing: .04em;
    font-size: .72rem !important; font-weight: 500 !important;
    padding: .4rem .85rem !important;
    border-right: 1px solid var(--rule) !important;
    cursor: pointer;
}}
div[data-testid="stTabs"] [data-testid="stTab"] p {{
    font-family: var(--mono) !important; text-transform: uppercase;
    letter-spacing: .04em; font-size: .72rem !important;
    font-weight: 500 !important; color: inherit !important;
}}
div[data-testid="stTabs"] button:hover,
div[data-testid="stTabs"] [data-testid="stTab"]:hover {{
    background: #17171b !important; color: var(--ink) !important;
}}
div[data-testid="stTabs"] button[aria-selected="true"],
div[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] {{
    background: var(--accent) !important; color: {BG} !important; font-weight: 600 !important;
}}
div[data-testid="stTabs"] button[aria-selected="true"] *,
div[data-testid="stTabs"] [data-testid="stTab"][aria-selected="true"] * {{
    color: {BG} !important; font-weight: 600 !important;
}}
/* the underline Streamlit paints under the active tab is redundant: the solid
   block already marks the selection */
div[data-testid="stTabs"] [role="tablist"] + div[data-rac],
div[data-testid="stTabs"] [role="tablist"] > div[data-rac]:not([data-testid]) {{
    background: transparent !important;
}}

/* Buttons and inputs */
.stButton > button, .stDownloadButton > button {{
    background: var(--accent) !important; color: {BG} !important;
    font-family: var(--mono) !important; text-transform: uppercase;
    letter-spacing: .05em; font-weight: 600 !important;
    border: 1.5px solid var(--rule) !important;
}}
[data-baseweb="select"] > div, [data-baseweb="input"] > div, [data-baseweb="base-input"] {{
    border-radius: 0 !important; border-color: var(--rule) !important;
    background: var(--card) !important;
}}
span[data-baseweb="tag"] {{
    background: var(--accent) !important; font-family: var(--mono) !important;
    font-size: .72rem !important;
}}
span[data-baseweb="tag"], span[data-baseweb="tag"] * {{ color: {BG} !important; }}
[role="radiogroup"] label {{ font-family: var(--mono) !important; font-size: .78rem !important; }}

[data-testid="stCaptionContainer"], .stCaption {{
    color: var(--muted) !important; font-family: var(--mono) !important;
    letter-spacing: .02em; font-size: .72rem !important;
}}

/* Reading block: the "so what" in prose, with a rule on the left */
.note {{
    border-left: 3px solid var(--accent);
    background: var(--card);
    padding: .95rem 1.3rem .95rem 1.25rem; margin: .1rem 0 1.3rem 0;
    font-size: .93rem; line-height: 1.55; color: var(--ink);
}}
.note.warn    {{ border-left-color: {WARN}; }}
.note.serious {{ border-left-color: {SERIOUS}; }}
.note.good    {{ border-left-color: {GOOD}; }}
.note b, .note strong {{ color: var(--ink); }}
.note code {{
    font-family: var(--mono); font-size: .84em; color: var(--ink);
    background: #1b1b20; padding: .06em .34em;
}}
.eyebrow {{
    font-family: var(--mono); text-transform: uppercase; letter-spacing: .09em;
    font-size: .66rem; color: var(--muted); margin-bottom: .25rem;
}}
.tag {{
    font-family: var(--mono); font-size: .64rem; text-transform: uppercase;
    letter-spacing: .06em; padding: .12em .45em; border: 1px solid var(--rule);
    color: var(--ink-2); margin-right: .3rem;
}}
hr {{ border-color: var(--rule) !important; }}
</style>
"""


# ---------------------------------------------------------------------------
# Device mockup
# ---------------------------------------------------------------------------
#: Phone screens drawn in CSS, with no images and no dependencies. They show
#: *what each party sees* at the same instant: the user gets the detail, the
#: guardian gets a coarse card. The asymmetry reads at a glance, which is more
#: convincing than explaining it.
#: Straight and unrounded on purpose: this is a schematic, not skeuomorphism,
#: and it fits the rest of the grid.
PHONE_CSS = f"""
<style>
.phone {{
    width: 100%; max-width: 320px; margin: 0 auto;
    border: 1.5px solid {RULE}; background: {BG};
    font-family: {SANS}; color: {INK};
}}
.phone-bar {{
    display: flex; justify-content: space-between; align-items: center;
    padding: .35rem .7rem; border-bottom: 1px solid {RULE};
    font-family: {MONO}; font-size: .66rem; color: {INK_2};
    letter-spacing: .06em;
}}
.phone-body {{ padding: 1.1rem .95rem 1.4rem .95rem; min-height: 330px; }}
.phone-eyebrow {{
    font-family: {MONO}; font-size: .6rem; letter-spacing: .1em;
    text-transform: uppercase; color: {MUTED}; margin-bottom: .8rem;
}}
.phone-h {{ font-size: 1.15rem; font-weight: 700; line-height: 1.25; margin-bottom: .6rem; }}
.phone-p {{ font-size: .86rem; line-height: 1.5; color: {INK_2}; margin-bottom: .9rem; }}
.phone-big {{
    font-family: {MONO}; font-size: 2.6rem; font-weight: 600;
    line-height: 1; margin: .2rem 0 .1rem 0;
}}
.phone-row {{
    display: flex; justify-content: space-between; gap: .6rem;
    padding: .5rem 0; border-bottom: 1px solid {RULE_SOFT};
    font-family: {MONO}; font-size: .72rem;
}}
.phone-row span:first-child {{ color: {MUTED}; }}
.phone-row span:last-child {{ color: {INK}; text-align: right; }}
.phone-cta {{
    margin-top: 1.1rem; padding: .55rem .7rem; text-align: center;
    font-family: {MONO}; font-size: .7rem; letter-spacing: .06em;
    text-transform: uppercase; background: {ACCENT}; color: {BG}; font-weight: 600;
}}
.phone-cta.ghost {{ background: transparent; color: {INK_2}; border: 1px solid {RULE}; }}
.phone-note {{
    font-family: {MONO}; font-size: .62rem; color: {MUTED};
    margin-top: .8rem; line-height: 1.45;
}}
.phone-caption {{
    font-family: {MONO}; font-size: .66rem; letter-spacing: .06em;
    text-transform: uppercase; color: {MUTED};
    text-align: center; margin: .6rem auto 0 auto; max-width: 320px;
}}
</style>
"""


def phone(bar_left: str, bar_right: str, inner: str) -> str:
    return (f'<div class="phone"><div class="phone-bar">'
            f'<span>{bar_left}</span><span>{bar_right}</span></div>'
            f'<div class="phone-body">{inner}</div></div>')


#: A gap when there is nothing to show. Deliberately quiet: it competes in the
#: same grid as the phone cards, but not in visual weight.
CSS += """
<style>
.empty {
    border: 1.5px dashed %s;
    color: %s;
    font-family: %s;
    font-size: .72rem;
    letter-spacing: .06em;
    text-transform: uppercase;
    text-align: center;
    padding: 2.4rem 1rem;
    max-width: 320px;
    margin: 0 auto;
}
</style>
""" % (RULE, MUTED, MONO)
