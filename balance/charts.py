"""
Layer 3 · figures. None of them decides anything: they receive frames already
computed.

Rules honoured across all of them (from the `dataviz` skill):
* never two Y axes: two different magnitudes are two charts;
* colour follows the entity (user, category), never its rank;
* with 2 or more series there is always a legend, and with 4 or fewer also
  direct labels;
* 2 px of surface gap between stacked fills (`marker_line` in the panel colour);
* recessive grid and axes, thin marks.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .theme import (
    CARD, CATEGORICAL, CATEGORY_COLOR, GOOD, INK, INK_2, MONO, MUTED, RULE,
    SERIOUS, USER_COLOR, WARN,
)

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _direct_label(fig, x, y, text, color, dx=6):
    fig.add_annotation(x=x, y=y, text=f" {text}", showarrow=False,
                       xanchor="left", yanchor="middle", xshift=dx,
                       font=dict(family=MONO, size=11, color=color))


def _frame(fig, h=340, legend=True, **kw):
    fig.update_layout(height=h, showlegend=legend, **kw)
    return fig


# ---------------------------------------------------------------------------
# Time series
# ---------------------------------------------------------------------------

def compare_line(frames: dict[str, pd.DataFrame], col: str, title: str,
                 unit: str = "", smooth: int = 7, h: int = 340) -> go.Figure:
    """One smoothed line per user, with the raw daily point behind it.

    The smoothing is what you read; the daily point sits behind at low opacity
    so the real variance is not hidden.
    """
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        fig.add_trace(go.Scatter(
            x=df["day"], y=df[col], mode="markers",
            marker=dict(size=4, color=c, opacity=.28),
            name=f"{user} · daily", legendgroup=user, showlegend=False,
            hovertemplate="%{y:.0f} " + unit + "<extra>User " + user + "</extra>",
        ))
        sm = df[col].rolling(smooth, min_periods=2, center=True).mean()
        fig.add_trace(go.Scatter(
            x=df["day"], y=sm, mode="lines", line=dict(color=c, width=2.4),
            name=f"User {user}", legendgroup=user,
            hovertemplate="%{y:.0f} " + unit + " (" + str(smooth) + "d mean)"
                          "<extra>User " + user + "</extra>",
        ))
        _direct_label(fig, df["day"].iloc[-1], sm.iloc[-1], user, c)
    fig.update_layout(title=title, yaxis_title=unit)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def daily_bars_vs_baseline(df: pd.DataFrame, col: str, baseline: str,
                           title: str, unit: str, user: str,
                           h: int = 320) -> go.Figure:
    """A daily bar against the personal 14-day rolling median.

    This is how a number comes to mean something: not "2 h of screen", but "2 h,
    half an hour less than normal for you".
    """
    c = USER_COLOR[user]
    over = (df[col] > df[baseline]).fillna(False)

    # Two traces instead of one with mixed colours: this way the amber enters
    # the legend and explains itself, with no caption to read.
    fig = go.Figure()
    for mask, name, color in (
        (~over, "At or below your normal", c),
        (over, "Above your normal", WARN),
    ):
        fig.add_trace(go.Bar(
            x=df["day"][mask], y=df[col][mask], name=name,
            marker=dict(color=color, line=dict(color=CARD, width=1.5)),
            hovertemplate="%{x|%a %d %b}<br>%{y:.0f} " + unit + "<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=df["day"], y=df[baseline], mode="lines",
        line=dict(color=INK, width=1.6, dash="dot"),
        name="Your normal (14-day median)",
        hovertemplate="normal: %{y:.0f} " + unit + "<extra></extra>",
    ))
    fig.update_layout(title=title, yaxis_title=unit, bargap=.25,
                      barmode="overlay", margin=dict(t=48, r=24, b=86, l=56),
                      legend=dict(y=-0.22))
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h + 20)


def day_span(df: pd.DataFrame, user: str, h: int = 340) -> go.Figure:
    """From the first unlock to the last screen-off, day by day.

    The axis starts at 04:00 so the small hours sit *at the top* (24 to 28)
    instead of dropping to the floor of the chart. The bar is the day with the
    phone; what spills over the top is what is eating into the night.
    """
    c = USER_COLOR[user]
    start = df["first_pickup_h"]
    end = df["last_use_h"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["day"], y=(end - start), base=start,
        marker=dict(color=c, opacity=.55, line=dict(color=CARD, width=1.2)),
        name="Day with the phone",
        customdata=list(zip(df["first_pickup_clock"], df["last_use_clock"])),
        hovertemplate="%{x|%a %d %b}<br>from %{customdata[0]} to %{customdata[1]}"
                      "<extra></extra>",
    ))
    fig.add_hline(y=23, line=dict(color=WARN, width=1.2, dash="dot"),
                  annotation_text="23:00",
                  annotation_position="right",
                  annotation_font=dict(family=MONO, size=10, color=WARN))
    fig.add_trace(go.Scatter(
        x=df["day"], y=end.rolling(7, min_periods=2, center=True).mean(),
        mode="lines", line=dict(color=INK, width=2),
        name="Last screen (7-day mean)", hoverinfo="skip",
    ))
    lo = max(5, int(start.min()) - 1)
    hi = min(29, int(end.max()) + 2)
    ticks = list(range(lo + lo % 2, hi + 1, 2))
    fig.update_layout(title=f"User {user} · from what time to what time",
                      yaxis_title="local time")
    fig.update_yaxes(tickvals=ticks,
                     ticktext=[f"{t % 24:02d}:00" for t in ticks], range=[lo, hi])
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def night_drift(frames: dict[str, pd.DataFrame], h: int = 340) -> go.Figure:
    """Screen minutes between 23:00 and 06:00, per night."""
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        # A series flat at zero reads as "data missing" unless you say so, and
        # the note goes in the legend, not in an annotation: over the bars it
        # covered what has to be read, and over the title it collided with it.
        flat = df["night_min"].max() < 0.5
        label = (f"User {user}: 0 min across {len(df)} nights" if flat
                 else f"User {user}")
        fig.add_trace(go.Bar(
            x=df["day"], y=df["night_min"], name=label,
            marker=dict(color=c, line=dict(color=CARD, width=1.2)),
            hovertemplate="%{x|%a %d %b}<br>%{y:.0f} late-night min"
                          "<extra>User " + user + "</extra>",
        ))
    fig.update_layout(title="Screen in the night band (23:00 to 06:00)",
                      yaxis_title="minutes", barmode="group", bargap=.2)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

def category_area(cat_daily: pd.DataFrame, title: str, h: int = 360) -> go.Figure:
    """Minutes per category and day, stacked. Fixed order, never by rank."""
    order = [c for c in CATEGORY_COLOR if c in set(cat_daily["category"])]
    wide = (cat_daily.pivot_table(index="day", columns="category",
                                  values="minutes", aggfunc="sum")
            .reindex(columns=order).fillna(0))
    roll = wide.rolling(3, min_periods=1, center=True).mean()
    fig = go.Figure()
    for cat in order:
        fig.add_trace(go.Scatter(
            x=roll.index, y=roll[cat], mode="lines", stackgroup="one",
            name=cat.replace("_", " ").title(),
            line=dict(width=1.2, color=CARD),
            fillcolor=CATEGORY_COLOR[cat],
            hovertemplate="%{y:.0f} min<extra>" + cat + "</extra>",
        ))
    fig.update_layout(title=title, yaxis_title="minutes (3-day rolling mean)")
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def top_bars(tot: pd.DataFrame, title: str, n: int = 10,
             h: int = 380) -> go.Figure:
    """Horizontal ranking by minutes, coloured by category."""
    d = tot.head(n).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["minutes"], y=d["label"], orientation="h",
        marker=dict(color=[CATEGORY_COLOR.get(c, MUTED) for c in d["category"]],
                    line=dict(color=CARD, width=1.5)),
        text=[f"{m:,.0f} min" for m in d["minutes"]],
        textposition="outside",
        textfont=dict(family=MONO, size=11, color=INK_2),
        customdata=d[["opens", "min_per_open", "category"]].values,
        hovertemplate="<b>%{y}</b><br>%{x:.0f} min totales<br>"
                      "%{customdata[0]} openings · %{customdata[1]:.1f} min per opening"
                      "<br>%{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(title=title, xaxis_title="minutes this month", bargap=.28,
                      margin=dict(t=48, r=48, b=56, l=110))
    fig.update_xaxes(range=[0, d["minutes"].max() * 1.24])
    fig.update_yaxes(tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h, legend=False)


def hour_heat(hh: pd.DataFrame, user: str, h: int = 330) -> go.Figure:
    """Weekly clock: screen minutes by weekday and hour."""
    grid = (hh.pivot_table(index="dow", columns="hour", values="minutes",
                           aggfunc="sum")
            .reindex(index=range(7), columns=range(24)).fillna(0))
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=list(range(24)), y=DOW,
        colorscale=[[0, "#131317"], [.2, "#17324f"], [.45, "#1f5ca3"],
                    [.75, "#3d86d8"], [1, "#7fb6f2"]],
        xgap=2, ygap=2,
        colorbar=dict(title=dict(text="min", font=dict(family=MONO, size=10,
                                                      color=INK_2)),
                      tickfont=dict(family=MONO, size=10, color=INK_2),
                      outlinewidth=0, thickness=9, len=.8, x=1.02),
        hovertemplate="%{y} · %{x}:00<br>%{z:.0f} min<extra></extra>",
    ))
    fig.update_layout(title=f"User {user} · weekly screen clock",
                      xaxis_title="local time")
    fig.update_xaxes(dtick=2, showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed",
                     tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h, legend=False, hovermode="closest")


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------

def blocks_daily(bf: pd.DataFrame, title: str, h: int = 340) -> go.Figure:
    """Blocked attempts per day, stacked by category."""
    order = [c for c in CATEGORY_COLOR if c in set(bf["category"])]
    wide = (bf.pivot_table(index="day", columns="category", values="target",
                           aggfunc="count").reindex(columns=order).fillna(0))
    fig = go.Figure()
    for cat in order:
        fig.add_trace(go.Bar(
            x=wide.index, y=wide[cat], name=cat.replace("_", " ").title(),
            marker=dict(color=CATEGORY_COLOR[cat],
                        line=dict(color=CARD, width=1.2)),
            hovertemplate="%{y:.0f}<extra>" + cat + "</extra>",
        ))
    fig.update_layout(title=title, yaxis_title="blocked attempts",
                      barmode="stack", bargap=.2)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def blocks_by_hour(bf: pd.DataFrame, title: str, h: int = 300) -> go.Figure:
    """What time the wall gets hit; sensitive against the rest."""
    sens = bf[bf["category"].isin(["ADULT", "GAMBLING"])]
    rest = bf[~bf["category"].isin(["ADULT", "GAMBLING"])]
    fig = go.Figure()
    for name, d, color in (("Ordinary distraction", rest, "#3987e5"),
                           ("Adult / gambling", sens, "#e66767")):
        counts = d.groupby("hour").size().reindex(range(24)).fillna(0)
        fig.add_trace(go.Bar(
            x=list(range(24)), y=counts.values, name=name,
            marker=dict(color=color, line=dict(color=CARD, width=1.2)),
            hovertemplate="%{x}:00 → %{y:.0f}<extra>" + name + "</extra>",
        ))
    fig.update_layout(title=title, xaxis_title="local time",
                      yaxis_title="attempts this month", barmode="stack", bargap=.15,
                      margin=dict(t=48, r=24, b=96, l=56),
                      legend=dict(y=-0.3))
    fig.update_xaxes(dtick=2)
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def score_line(frames: dict[str, pd.DataFrame], h: int = 340) -> go.Figure:
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["score"], mode="markers",
            marker=dict(size=4, color=c, opacity=.3),
            name=f"{user} daily", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["score_7d"], mode="lines",
            line=dict(color=c, width=2.6), name=f"User {user}",
            hovertemplate="%{y:.0f}/100<extra>User " + user + "</extra>"))
        _direct_label(fig, df["day"].iloc[-1], df["score_7d"].iloc[-1], user, c)
    fig.update_layout(title="Digital wellbeing index (7-day mean)",
                      yaxis_title="0 to 100")
    fig.update_yaxes(range=[0, 100], dtick=20)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def score_breakdown(contrib: pd.DataFrame, user: str, h: int = 300) -> go.Figure:
    """How many points each component contributes and how many it lets go."""
    d = contrib.iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["points"], y=d["component"], orientation="h", name="Points earned",
        marker=dict(color=USER_COLOR[user], line=dict(color=CARD, width=1.5)),
        hovertemplate="%{x:.1f} of %{customdata:.0f} possible<extra></extra>",
        customdata=d["weight"] * 100))
    fig.add_trace(go.Bar(
        x=d["lost"], y=d["component"], orientation="h", name="Points lost",
        marker=dict(color="#33333a", line=dict(color=CARD, width=1.5)),
        hovertemplate="%{x:.1f} lost<extra></extra>"))
    fig.update_layout(title=f"User {user} · where the index comes from (month mean)",
                      barmode="stack", bargap=.3, xaxis_title="points out of 100")
    fig.update_yaxes(tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Month walkthrough
# ---------------------------------------------------------------------------

#: (column, label, unit, colour slot, dash pattern, rules that read it)
#:
#: Every series is expressed as a percentage of its own maximum for the period,
#: which is what puts seven different magnitudes on one axis. It is not a
#: disguised second scale; it is a single scale with a declared transform, and
#: the real value with its unit travels in the tooltip. It divides by the
#: maximum rather than rescaling min-max because zero has to stay zero: for
#: user A, "zero late-night minutes" is the data, and min-max would paint it
#: halfway up.
#:
#: The dash pattern is not decorative. Validating the palette against the dark
#: surface leaves the worst adjacent pair (green ↔ yellow) at ΔE 10.3, inside
#: the floor band for protan colour blindness, where the rule is that a
#: secondary encoding is required. With seven overlapping series and a legend
#: only, the stroke is that encoding: each series is distinguishable even when
#: the colour does not land.
TRACKED = [
    ("night_min", "Late-night screen", "min", 0, "solid",
     "night_drift · night_streak"),
    ("night_end_min", "Last screen (from 23:00)", "min", 1, "dash",
     "night_drift"),
    ("screen_min", "Screen per day", "min", 2, "solid", "screen_jump"),
    ("longest_offline_h", "Longest disconnection", "h", 3, "dot",
     "offline_record"),
    ("blocks", "Blocks per day", "", 4, "dashdot", "calm_week"),
    ("blocks_sensitive", "Sensitive attempts", "", 5, "dash",
     "sensitive_spike · filter_calm"),
    ("distract_pct", "Distraction share", "%", 6, "dot", "focus_week"),
]

#: Series visible on open. The rest come in with a legend click: seven lines at
#: once do not read, and starting with all of them on forces the reader to
#: switch things off rather than on.
TRACKED_DEFAULT = {"night_min", "night_end_min", "screen_min"}

#: Height of the event rail, below the data zero.
_RAIL = -9


def _derive_tracked(df: pd.DataFrame) -> pd.DataFrame:
    """Derived columns that exist only for this chart."""
    df = df.copy()
    # The time of the last screen is expressed as minutes past 23:00, so zero
    # means "went dark on time" rather than "midnight".
    df["night_end_min"] = (df["night_end_h"] - 23) * 60
    df["longest_offline_h"] = df["longest_offline_s"] / 3600
    df["distract_pct"] = df["distract_share"] * 100
    return df


def tracked_series(df: pd.DataFrame, user: str, cursor,
                   nudge_days: set, alert_days: dict, positive_days: dict,
                   h: int = 560):
    """Every watched variable on one axis, switchable from the legend.

    Each series runs as a percentage of its own maximum for the period, which is
    what allows them to be compared without a second Y axis. What you read is
    the shape and the coincidence in time, not the level; the level is in the
    tooltip and in the weekly summary.

    Below zero sits an event rail with what the phone emitted each day. It
    switches on and off from the legend too, and it shares the time axis with
    the data that explains it.
    """
    d = _derive_tracked(df)
    fig = go.Figure()

    for i, (col, label, unit, slot, trazo, reglas) in enumerate(TRACKED):
        serie = d[col]
        tope = serie.max()
        if pd.isna(tope) or tope <= 0:
            # Series flat at zero: drawn anyway, hugging the axis, so it is
            # visible that the data exists and is zero.
            norm = serie.fillna(0) * 0
            note_ = " · no activity"
        else:
            norm = serie / tope * 100
            note_ = ""
        fig.add_trace(go.Scatter(
            x=d["day"], y=norm, mode="lines+markers",
            name=f"{label}{note_}",
            # The group only titles the legend. With
            # `groupclick="toggleitem"` each entry toggles on its own; without
            # that option, Plotly switches the whole group off in one click.
            legendgroup="datos",
            legendgrouptitle=dict(text="Watched variables") if i == 0 else None,
            visible=True if col in TRACKED_DEFAULT else "legendonly",
            line=dict(color=CATEGORICAL[slot], width=2, dash=trazo),
            marker=dict(size=5, color=CATEGORICAL[slot],
                        symbol=["circle", "square", "diamond", "cross",
                                "x", "triangle-up", "pentagon"][slot]),
            customdata=serie,
            hovertemplate=("<b>" + label + "</b>: %{customdata:.1f} " + unit
                           + "<br>" + reglas + "<extra></extra>"),
        ))

    # --- event rail ---------------------------------------------------------
    events = [
        ("Night with a nudge", sorted(nudge_days), "circle", WARN,
         "Night nudge on the device"),
        ("Guardian alert",
         sorted(k for k, v in alert_days.items() if v == "sent"),
         "triangle-up", SERIOUS, "Notification sent to the guardian"),
        ("Summary entry",
         sorted(k for k, v in alert_days.items() if v == "summary"),
         "diamond", INK_2, "Signal held for the weekly summary"),
        ("Reinforcement", sorted(positive_days), "star", GOOD,
         "Reinforcement sent"),
    ]
    for i, (name, days, symbol, color, detail) in enumerate(events):
        fig.add_trace(go.Scatter(
            x=days, y=[_RAIL] * len(days), mode="markers", name=name,
            legendgroup="events",
            legendgrouptitle=dict(text="Emissions") if i == 0 else None,
            marker=dict(symbol=symbol, size=11, color=color,
                        line=dict(color=CARD, width=1)),
            hovertemplate="%{x|%d %b}<br>" + detail + "<extra></extra>",
            showlegend=True,
        ))

    fig.add_hline(y=0, line=dict(color=RULE, width=1))
    fig.add_vline(x=cursor, line=dict(color=INK, width=2))

    fig.update_layout(
        height=h, hovermode="x unified",
        yaxis_title="% of the period maximum",
        margin=dict(t=44, r=24, b=120, l=64),
        legend=dict(orientation="h", y=-0.24, x=0, xanchor="left",
                    yanchor="top", groupclick="toggleitem",
                    font=dict(family=MONO, size=11, color=INK_2),
                    grouptitlefont=dict(family=MONO, size=11, color=MUTED)),
    )
    fig.update_yaxes(range=[_RAIL - 5, 108], dtick=25,
                     tickvals=[0, 25, 50, 75, 100],
                     ticktext=["0", "25", "50", "75", "100 %"])
    fig.update_xaxes(tickformat="%d %b")
    fig.add_annotation(xref="paper", x=0, y=_RAIL, yanchor="middle",
                       xanchor="right", xshift=-8, text="events",
                       showarrow=False,
                       font=dict(family=MONO, size=10, color=MUTED))
    return fig


# ---------------------------------------------------------------------------
# Weekly summary
# ---------------------------------------------------------------------------

def week_evolution(w: pd.DataFrame, col: str, label: str, unit: str,
                   user: str, sel: int, h: int = 260) -> go.Figure:
    """One magnitude week by week, with the selected week highlighted.

    Short weeks are hollow and labelled: a two-day week averaged next to a
    seven-day one reads as a drop that never happened.
    """
    c = USER_COLOR[user]
    labels = [f"W{i}" + (" *" if p else "") for i, p in zip(w.index, w["is_partial"])]
    fig = go.Figure(go.Bar(
        x=labels, y=w[col],
        marker=dict(color=[c if i == sel else "#2f2f36" for i in w.index],
                    line=dict(color=CARD, width=1.5)),
        text=[f"{v:,.0f}" if abs(v) >= 10 else f"{v:,.1f}" for v in w[col]],
        textposition="outside",
        textfont=dict(family=MONO, size=11, color=INK_2),
        hovertemplate="%{x}<br>%{y:.1f} " + unit + "<extra>" + label + "</extra>",
    ))
    fig.update_layout(title=label, yaxis_title=unit, bargap=.35,
                      height=h, showlegend=False,
                      margin=dict(t=44, r=20, b=36, l=54))
    fig.update_yaxes(range=[0, max(w[col].max() * 1.25, 0.1)])
    return fig


def week_days(df: pd.DataFrame, week: int, col: str, label: str, unit: str,
              user: str, h: int = 300) -> go.Figure:
    """The days of the selected week against the mean of previous weeks."""
    cur = df[df["week"] == week]
    prev = df[df["week"] < week]
    ref = prev[col].mean() if len(prev) else None

    fig = go.Figure(go.Bar(
        x=[DOW[d] for d in cur["dow"]], y=cur[col],
        marker=dict(color=USER_COLOR[user], line=dict(color=CARD, width=1.5)),
        name=f"Week {week}",
        hovertemplate="%{x}<br>%{y:.0f} " + unit + "<extra></extra>",
    ))
    if ref is not None:
        fig.add_hline(y=ref, line=dict(color=INK, width=1.6, dash="dot"),
                      annotation_text=f"mean of previous weeks: {ref:,.0f}",
                      annotation_position="top left",
                      annotation_font=dict(family=MONO, size=10, color=INK_2))
    if cur[col].abs().max() == 0:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="No activity this week", showarrow=False,
                           font=dict(family=MONO, size=11, color=MUTED))
        fig.update_yaxes(range=[0, 1], showticklabels=False)
    fig.update_layout(title=label, yaxis_title=unit, bargap=.3, height=h,
                      showlegend=False, margin=dict(t=52, r=20, b=40, l=54))
    return fig


def week_components(w: pd.DataFrame, sel: int, h: int = 320) -> go.Figure:
    """The five index components, week by week.

    This is where you see which part of the index moves and which stays put,
    which is the question that follows "the index went down".
    """
    from .score import COMPONENTS
    fig = go.Figure()
    labels = [f"W{i}" for i in w.index]
    for (col, label, *_rest), color in zip(COMPONENTS, CATEGORICAL):
        fig.add_trace(go.Scatter(
            x=labels, y=w[f"score_{col}"], mode="lines+markers", name=label,
            line=dict(color=color, width=2.2), marker=dict(size=8, color=color),
            hovertemplate="%{y:.0f}/100<extra>" + label + "</extra>",
        ))
    fig.add_vline(x=f"W{sel}", line=dict(color=INK, width=1.6, dash="dot"))
    fig.update_layout(title="Index components by week",
                      yaxis_title="0 to 100", height=h,
                      margin=dict(t=44, r=20, b=76, l=54))
    fig.update_yaxes(range=[0, 105], dtick=25)
    return fig
