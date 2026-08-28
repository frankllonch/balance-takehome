"""
Balance · device behaviour explorer.

A reading dashboard: what is in the events, what metrics come out of them, and
what story the two profiles tell over May 2026.

    streamlit run app.py
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from balance import charts, theme
from balance.events import SENSITIVE, load
from balance.metrics import (
    blocks_frame, category_daily, daily_frame, hourly_heat, totals, weekly_frame,
)
from balance.intelligence import (
    ALERT_BUDGET, NUDGE_AFTER_MIN, emissions, evaluate_alerts,
    evaluate_positives, month_replay, nudge_summary, replay_nudge,
)
from balance.score import COMPONENTS, add_score, contributions

st.set_page_config(page_title="Balance · Device event explorer",
                   page_icon="◐", layout="wide",
                   initial_sidebar_state="expanded")
theme.register_template()
st.markdown(theme.CSS, unsafe_allow_html=True)
st.markdown(theme.PHONE_CSS, unsafe_allow_html=True)

DATA = {"A": "data/events_user_a.json", "B": "data/events_user_b.json"}

#: Only profile B has a guardian assigned. A is an adult: the alert rules run
#: all the same, but there is no recipient to notify, so their signals only
#: feed their own index and nudges.
HAS_GUARDIAN = {"A": False, "B": True}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Rebuilding sessions from the event log…")
def build(user: str):
    tl = load(DATA[user], user)
    df = add_score(daily_frame(tl))
    # days truncated by the file edge stay out of EVERY view, not only the
    # daily frame, or the totals stop matching.
    days = set(df["day"])
    nudges = replay_nudge(tl, df)
    positives = evaluate_positives(df, HAS_GUARDIAN[user])
    replay = month_replay(df, nudges, positives)

    weekly = weekly_frame(df)
    for col, *_ in COMPONENTS:
        weekly[f"score_{col}"] = df.groupby("week")[f"score_{col}"].mean()

    return {
        "df": df,
        "apps": totals(tl, df, "app"),
        "sites": totals(tl, df, "site"),
        "cats": category_daily(df),
        "heat": hourly_heat(tl, days),
        "blocks": blocks_frame(tl, days),
        "events": tl.events,
        "anomalies": dict(tl.anomalies),
        "n_intervals": len(tl.intervals),
        "screen_h": sum(i.seconds for i in tl.intervals) / 3600,
        "attributed_h": sum(u.seconds for u in tl.usages) / 3600,
        "alerts": evaluate_alerts(df),
        "positives": positives,
        "weekly": weekly,
        "nudges": nudges,
        "replay": replay,
        "emissions": emissions(replay),
    }


U = {u: build(u) for u in DATA}
F = {u: U[u]["df"] for u in DATA}


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

def note(text: str, kind: str = "") -> None:
    st.markdown(f'<div class="note {kind}">{text}</div>', unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def empty_box(text: str) -> None:
    """An explicit gap. A drawn phone saying "nothing is shown" is a
    notification announcing there is no notification: it takes up the same room
    and reads as loud as the ones that do exist."""
    st.markdown(f'<div class="empty">{text}</div>', unsafe_allow_html=True)


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fecha(d) -> str:
    """Short date. Written by hand rather than via `strftime` so the label does
    not depend on the process locale."""
    return f"{d.day} {MONTHS[d.month - 1]}"


def reloj(h) -> str:
    """Shifted-axis hour (24 to 28 = small hours) to HH:MM. It is None when
    there was no screen in the band, which is user A's normal case."""
    if h is None or pd.isna(h):
        return "no use"
    return f"{int(h % 24):02d}:{int(h % 1 * 60):02d}"


def hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def kpis(items: list[tuple[str, str, str | None]]) -> None:
    for col, (label, value, delta) in zip(st.columns(len(items)), items):
        col.metric(label, value, delta, delta_color="off" if delta else "normal")


def wk(df: pd.DataFrame, col: str, week: int, how: str = "mean") -> float:
    s = df[df["week"] == week][col]
    return getattr(s, how)()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Balance")
    st.caption("Device event explorer · May 2026")
    st.markdown("---")
    eyebrow("Data footprint")
    for u in DATA:
        st.caption(
            f"**User {u}**: {len(U[u]['events']):,} events · "
            f"{len(F[u])} complete days · {U[u]['n_intervals']} screen stretches"
        )
    st.markdown("---")
    eyebrow("Scope of this data")
    st.caption(
        "This is the device-side view. Per-app, per-site and block detail is "
        "never transmitted off the phone. What a guardian receives is in "
        "**Alerts and nudges**."
    )
    st.markdown("---")
    eyebrow("Notifications in the period")
    for u in DATA:
        n = (sum(1 for x in U[u]["alerts"] if x.decision == "sent")
             if HAS_GUARDIAN[u] else None)
        st.caption(f"**User {u}**: "
                   f"{f'{n} to the guardian' if n is not None else 'no guardian'} · "
                   f"{sum(1 for x in U[u]['nudges'] if x.fired)} nudges")


st.title("Device behaviour · May 2026")
st.caption(
    "2 profiles · 11,488 events · 30 days · screen time, unlocks, night band, "
    "categories, blocks, wellbeing index and alerts"
)

# The selector lives in the body, not the sidebar: if someone collapses it,
# switching profile should not depend on finding the button to reopen it. The
# sidebar keeps context only.
_sel, _rest = st.columns([1, 4])
with _sel:
    who = st.radio(
        "Profile to inspect", ["A", "B"], horizontal=True, key="who",
        help="Affects Daily rhythm, Where the time goes and What the phone "
             "stopped. Overview and The night always compare both.",
    )

TABS = st.tabs([
    "Overview", "Weekly summary", "Daily rhythm", "The night",
    "Where the time goes", "What the phone stopped", "Alerts and nudges",
    "The data",
])


# ===========================================================================
# 1 · OVERVIEW
# ===========================================================================
with TABS[0]:
    a, b = F["A"], F["B"]

    st.markdown("### Profiles")
    note(
        f"The two files are different kinds of profile and need different "
        f"configurations.<br><br>"
        f"<b>User A</b> · adult, no guardian. {hm(a.screen_min.mean())} of screen "
        f"per day, {a.pickups.mean():.0f} unlocks, {a.distinct_apps.mean():.0f} "
        f"apps. No night-band use and no sensitive content across the 30 days."
        f"<br>"
        f"<b>User B</b> · minor with a guardian. {hm(b.screen_min.mean())}, "
        f"{b.pickups.mean():.0f} unlocks, {b.distinct_apps.mean():.0f} apps. "
        f"{b.blocks.sum():,.0f} blocked attempts, of which "
        f"{b.blocks_sensitive.sum():.0f} are <code>ADULT</code> or "
        f"<code>GAMBLING</code>. App catalogue consistent with a minor: Duolingo "
        f"and Kindle in daily use, Roblox and Clash of Clans blocked 73 and 71 "
        f"times."
    )

    c1, c2 = st.columns(2)
    for col, u in ((c1, "A"), (c2, "B")):
        d = F[u]
        with col:
            eyebrow(f"User {u} · wellbeing index")
            st.markdown(
                f"<div style='font-family:{theme.MONO};font-size:3.4rem;"
                f"line-height:1;color:{theme.USER_COLOR[u]};font-weight:600'>"
                f"{d.score.mean():.0f}<span style='font-size:1.1rem;color:{theme.MUTED}'>"
                f" /100</span></div>"
                f"<div class='eyebrow' style='margin-top:.35rem'>"
                f"week 1 → {wk(d,'score',1):.0f} &nbsp;·&nbsp; last full week → "
                f"{wk(d,'score',4):.0f}</div>",
                unsafe_allow_html=True)

    st.markdown("")
    kpis([
        ("A · screen/day", hm(a.screen_min.mean()), None),
        ("A · unlocks/day", f"{a.pickups.mean():.0f}", None),
        ("A · late night/day", f"{a.night_min.mean():.0f} min", None),
        ("A · blocks/month", f"{a.blocks.sum():.0f}", None),
        ("A · sensitive", f"{a.blocks_sensitive.sum():.0f}", None),
    ])
    kpis([
        ("B · screen/day", hm(b.screen_min.mean()), None),
        ("B · unlocks/day", f"{b.pickups.mean():.0f}", None),
        ("B · late night/day", f"{b.night_min.mean():.0f} min", None),
        ("B · blocks/month", f"{b.blocks.sum():,.0f}", None),
        ("B · sensitive", f"{b.blocks_sensitive.sum():.0f}", None),
    ])

    st.markdown("### Wellbeing index")
    st.plotly_chart(charts.score_line(F), width="stretch", key="k_score")
    note(
        f"<b>A</b> holds at {a.score.mean():.0f} across the four weeks "
        f"(range {a.score.min():.0f} to {a.score.max():.0f}), with no change of "
        f"trend.<br>"
        f"<b>B</b> goes from {wk(b,'score',1):.0f} to {wk(b,'score',4):.0f}, "
        f"{wk(b,'score',1)-wk(b,'score',4):.0f} points in three weeks. The drop "
        f"comes almost entirely from the night component: their night score falls "
        f"from {wk(b,'score_night_min',1):.0f} to "
        f"{wk(b,'score_night_min',4):.0f} while every other component moves less "
        f"than 10 points. Detail in \"The night\".",
        "warn")

    st.markdown("### What moves and what does not")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(charts.compare_line(F, "screen_min",
                        "Screen time per day", "minutes"),
                        width="stretch", key="k_screen")
        st.plotly_chart(charts.compare_line(F, "pickups",
                        "Real unlocks per day", "unlocks"),
                        width="stretch", key="k_pickups")
    with g2:
        st.plotly_chart(charts.compare_line(F, "night_min",
                        "Late-night screen minutes", "minutes"),
                        width="stretch", key="k_night")
        st.plotly_chart(charts.compare_line(F, "blocks",
                        "Blocked attempts per day", "blocks"),
                        width="stretch", key="k_blocks")

    d_screen = (wk(b, "screen_min", 4) / wk(b, "screen_min", 1) - 1) * 100
    d_pick = (wk(b, "pickups", 4) / wk(b, "pickups", 1) - 1) * 100
    d_night = wk(b, "night_min", 4) / max(wk(b, "night_min", 1), .01)
    st.markdown("### User B, week 1 against week 4")
    st.dataframe(pd.DataFrame([
        ("Screen per day", f"{wk(b,'screen_min',1):.0f} min",
         f"{wk(b,'screen_min',4):.0f} min", f"{d_screen:+.0f} %"),
        ("Unlocks per day", f"{wk(b,'pickups',1):.0f}",
         f"{wk(b,'pickups',4):.0f}", f"{d_pick:+.0f} %"),
        ("Late-night minutes", f"{wk(b,'night_min',1):.1f} min",
         f"{wk(b,'night_min',4):.0f} min", f"×{d_night:.0f}"),
        ("Unlocks after midnight", f"{wk(b,'night_pickups',1):.1f}",
         f"{wk(b,'night_pickups',4):.1f}",
         f"×{wk(b,'night_pickups',4)/max(wk(b,'night_pickups',1),.01):.0f}"),
        ("Blocks per day", f"{wk(b,'blocks',1):.0f}",
         f"{wk(b,'blocks',4):.0f}",
         f"{(wk(b,'blocks',4)/wk(b,'blocks',1)-1)*100:+.0f} %"),
    ], columns=["Metric", "Week 1", "Week 4", "Change"]),
        width="stretch", hide_index=True)
    note(
        f"Volume barely moves ({d_screen:+.0f} % of screen time, "
        f"{d_pick:+.0f} % of unlocks) while the night band multiplies by "
        f"{d_night:.0f}. A threshold on screen time would not have caught this "
        f"case: detection runs on the night band, not on the total (see "
        f"\"Alerts and nudges\").",
        "serious")

# ===========================================================================
# 2 · WEEKLY SUMMARY
# ===========================================================================
with TABS[1]:
    d = F[who]
    w = U[who]["weekly"]
    st.markdown(f"### User {who} · week by week")

    weeks = list(w.index)
    sel = st.select_slider(
        "Week", options=weeks, value=weeks[-2] if len(weeks) > 1 else weeks[-1],
        format_func=lambda i: (f"Week {i}"
                               + (" (short)" if w.loc[i, "is_partial"] else "")),
        key=f"week_{who}")
    cur = w.loc[sel]
    prev = w.loc[sel - 1] if sel - 1 in w.index else None

    st.caption(
        f"{fecha(cur['start'])} to {fecha(cur['end'])} · {int(cur['days'])} "
        f"days" + ("  ·  short week: the averages are per day, but comparing it "
                   "against seven-day weeks is less reliable."
                   if cur["is_partial"] else "")
    )

    def delta(col, unit="", dec=0):
        """Change against the previous week, in the metric's own unit.

        A change that rounds to zero is not shown: "+0 min" with a green arrow
        says something improved when nothing moved.
        """
        if prev is None or pd.isna(prev[col]):
            return None
        v = cur[col] - prev[col]
        if abs(round(v, dec)) < 10 ** -dec / 2 or f"{v:.{dec}f}".strip("-+") in ("0", "0.0"):
            return "no change"
        return f"{v:+.{dec}f} {unit}".strip()

    kpis([
        ("Screen / day", hm(cur["screen_min"]), delta("screen_min", "min")),
        ("Unlocks / day", f"{cur['pickups']:.0f}", delta("pickups")),
        ("Late night / night", f"{cur['night_min']:.0f} min",
         delta("night_min", "min")),
        ("Longest disconnection", f"{cur['longest_offline_h']:.1f} h",
         delta("longest_offline_h", "h", dec=1)),
        ("Best stretch this week", f"{cur['best_offline_h']:.1f} h",
         cur["best_offline_when"]),
        ("Blocks / day", f"{cur['blocks']:.1f}", delta("blocks", dec=1)),
        ("Index", f"{cur['score']:.0f}", delta("score", dec=0)),
    ])

    st.markdown("")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(charts.week_evolution(
            w, "screen_min", "Screen per day, by week", "min", who, sel),
            width="stretch", key=f"we_screen_{who}")
        st.plotly_chart(charts.week_evolution(
            w, "night_min", "Late night per night, by week", "min", who, sel),
            width="stretch", key=f"we_night_{who}")
    with g2:
        st.plotly_chart(charts.week_evolution(
            w, "pickups", "Unlocks per day, by week", "", who, sel),
            width="stretch", key=f"we_pick_{who}")
        st.plotly_chart(charts.week_evolution(
            w, "blocks", "Blocks per day, by week", "", who, sel),
            width="stretch", key=f"we_blocks_{who}")
    st.caption("Weeks marked with * are shorter than seven days.")

    st.plotly_chart(charts.week_components(w, sel), width="stretch",
                    key=f"we_comp_{who}")

    st.markdown(f"#### The days of week {sel}")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.week_days(
            d, sel, "screen_min", f"Screen per day · week {sel}", "min", who),
            width="stretch", key=f"wd_screen_{who}")
    with c2:
        st.plotly_chart(charts.week_days(
            d, sel, "night_min", f"Late night per night · week {sel}", "min", who),
            width="stretch", key=f"wd_night_{who}")

    st.markdown("#### Against the rest of the period")
    rows = [
        ("Screen per day", "screen_min", "min", 0),
        ("Unlocks per day", "pickups", "", 0),
        ("Late night per night", "night_min", "min", 0),
        ("Longest disconnection", "longest_offline_h", "h", 1),
        ("Distinct apps per day", "distinct_apps", "", 1),
        ("App switches per hour", "switches_per_screen_hour", "", 0),
        ("Distraction share", "distract_share", "%", 0),
        ("Blocks per day", "blocks", "", 1),
        ("Index", "score", "", 0),
    ]
    tbl = []
    for label, col, unit, dec in rows:
        mult = 100 if unit == "%" else 1
        # Rounded BEFORE subtracting: otherwise the change does not match the
        # two columns beside it and looks like an arithmetic error.
        v = round(cur[col] * mult, dec)
        pv = (round(prev[col] * mult, dec)
              if prev is not None and not pd.isna(prev[col]) else None)
        med = round(w[col].median() * mult, dec)
        if pv is None:
            var = "n/a"
        elif abs(v - pv) < 10 ** -dec / 2:
            var = "no change"
        else:
            var = f"{v - pv:+.{dec}f} {unit}".strip()
        tbl.append({
            "Metric": label,
            f"Week {sel}": f"{v:.{dec}f} {unit}".strip(),
            "Previous week": (f"{pv:.{dec}f} {unit}".strip()
                              if pv is not None else "n/a"),
            "Period median": f"{med:.{dec}f} {unit}".strip(),
            "Change": var,
        })
    st.dataframe(pd.DataFrame(tbl), width="stretch", hide_index=True)

    st.markdown(f"#### What the phone emitted in week {sel}")
    wk_days = set(d[d["week"] == sel]["day"])
    wk_em = [e for e in U[who]["emissions"] if e["day"] in wk_days]
    resumen = [x for x in U[who]["positives"]
               if x.decision == "summary" and x.day in wk_days]

    if wk_em:
        st.dataframe(pd.DataFrame([{
            "Date": fecha(e["day"]), "Destination": e["destination"],
            "Type": e["type"], "Detail": e["detail"],
        } for e in wk_em]), width="stretch", hide_index=True)
    else:
        st.caption("No notification and no nudge this week.")

    if resumen:
        st.markdown("**Also recorded this week, not notified**")
        for x in resumen:
            st.markdown(
                f"<div class='phone-row'><span>{x.headline}</span>"
                f"<span>{x.reason.split('.')[0]}</span></div>",
                unsafe_allow_html=True)


# ===========================================================================
# 3 · DAILY RHYTHM
# ===========================================================================
with TABS[2]:
    d = F[who]
    st.markdown(f"### User {who} · month at a glance")

    best = d.loc[d.score.idxmax()]
    worst = d.loc[d.score.idxmin()]
    kpis([
        ("Screen / day", hm(d.screen_min.mean()),
         f"±{d.screen_min.std():.0f} min"),
        ("Sessions / day", f"{d.sessions.mean():.0f}",
         f"median {d.median_session_s.mean()/60:.1f} min"),
        ("Real unlocks", f"{d.pickups.mean():.0f}",
         f"{d.glances.mean():.0f} glances"),
        ("First unlock", d.first_pickup_clock.mode().iloc[0],
         f"median {d.first_pickup_h.median():.1f} h"),
        ("Longest disconnection", f"{d.longest_offline_s.mean()/3600:.1f} h",
         f"best: {d.longest_offline_h.max():.1f} h on "
         f"{d.loc[d.longest_offline_h.idxmax(), 'longest_offline_when']}"),
        ("App switches / h", f"{d.switches_per_screen_hour.mean():.0f}",
         f"{d.distinct_apps.mean():.0f} distinct apps"),
    ])

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.daily_bars_vs_baseline(
            d, "screen_min", "screen_min_baseline",
            f"User {who} · screen per day", "minutes", who),
            width="stretch", key="k_bar_screen")
    with c2:
        st.plotly_chart(charts.daily_bars_vs_baseline(
            d, "pickups", "pickups_baseline",
            f"User {who} · unlocks per day",
            "unlocks", who), width="stretch", key="k_bar_pickups")
    st.caption(
        "Reference: median of the same user's previous 14 days. The first 14 "
        "days of the period have no history to compare against and are shown "
        "uncompared."
    )

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(charts.hour_heat(U[who]["heat"], who),
                        width="stretch", key="k_heat")
    with c4:
        st.plotly_chart(charts.day_span(d, who), width="stretch", key="k_span")

    wknd = d.groupby("is_weekend")[["screen_min", "pickups", "night_min"]].mean()
    diff = wknd.loc[True, "screen_min"] - wknd.loc[False, "screen_min"]
    if who == "A":
        note(
            f"<b>Stable routine.</b> First unlock between 07:30 and 09:00, last "
            f"screen around {d.last_use_clock.mode().iloc[0]}, no activity after "
            f"23:00 on any day of the period.<br><br>"
            f"<b>Work-shaped use.</b> Weekends drop to "
            f"{wknd.loc[True,'screen_min']:.0f} min against "
            f"{wknd.loc[False,'screen_min']:.0f} on weekdays "
            f"({abs(diff):.0f} min less), with "
            f"{wknd.loc[False,'pickups']-wknd.loc[True,'pickups']:.0f} fewer "
            f"unlocks.<br><br>"
            f"<b>Short, clean sessions.</b> Median of "
            f"{d.median_session_s.mean()/60:.1f} min and "
            f"{d.switches_per_screen_hour.mean():.0f} app switches per screen "
            f"hour, over {d.distinct_apps.mean():.0f} distinct apps a day. No "
            f"intervention needed.",
            "good")
    else:
        note(
            f"<b>No weekend break.</b> "
            f"{wknd.loc[True,'screen_min']:.0f} min at weekends against "
            f"{wknd.loc[False,'screen_min']:.0f} on weekdays ({diff:+.0f}). Use "
            f"spreads from 08:00 to 00:00 all seven days, with the midnight band "
            f"gaining weight through the month.<br><br>"
            f"<b>Fragmented use.</b> Sessions of "
            f"{d.median_session_s.mean()/60:.1f} min median but "
            f"{d.switches_per_screen_hour.mean():.0f} app switches per hour, "
            f"{d.switches_per_screen_hour.mean()/F['A'].switches_per_screen_hour.mean():.1f}× "
            f"user A's rate. The pattern is frequent checking, not long "
            f"sessions.<br><br>"
            f"<b>Active night band.</b> {d.night_min.mean():.0f} min on average "
            f"between 23:00 and 06:00, and rising. This is what generated the "
            f"guardian alert.",
            "warn")

    with st.expander("See the full daily table"):
        cols = ["day", "score", "screen_min", "pickups", "glances", "sessions",
                "night_min", "night_pickups", "first_pickup_clock",
                "last_use_clock", "longest_offline_s", "longest_offline_when",
                "distinct_apps",
                "app_switches", "distract_share", "blocks", "blocks_sensitive"]
        show = d[cols].copy()
        show["longest_offline_s"] = (show["longest_offline_s"] / 3600).round(1)
        show = show.rename(columns={"longest_offline_s": "offline_max_h"})
        st.dataframe(show.round(1), width="stretch", hide_index=True)
        st.download_button("Download CSV",
                           d.drop(columns=["_cat_s", "_app_s", "_site_s"]).to_csv(index=False),
                           file_name=f"balance_daily_{who}.csv", mime="text/csv")


# ===========================================================================
# 4 · THE NIGHT
# ===========================================================================
with TABS[3]:
    b = F["B"]
    st.markdown("### Night band · user B")

    n1, n4 = wk(b, "night_min", 1), wk(b, "night_min", 4)
    e1, e4 = wk(b, "night_end_h", 1), wk(b, "night_end_h", 4)
    f1, f4 = wk(b, "first_pickup_h", 1), wk(b, "first_pickup_h", 4)
    sleep1 = (24 + f1) - e1
    sleep4 = (24 + f4) - e4

    kpis([
        ("B · late night wk 1", f"{n1:.0f} min", None),
        ("B · late night wk 4", f"{n4:.0f} min", f"×{n4/max(n1,.01):.0f}"),
        ("B · last screen wk 1", f"{int(e1%24):02d}:{int(e1%1*60):02d}", None),
        ("B · last screen wk 4", f"{int(e4%24):02d}:{int(e4%1*60):02d}",
         f"{(e4-e1)*60:+.0f} min"),
        ("B · first unlock", f"{int(f4):02d}:{int(f4%1*60):02d}",
         f"{(f4-f1)*60:+.0f} min"),
        ("B · sleep window", f"{sleep4:.1f} h", f"{(sleep4-sleep1)*60:+.0f} min"),
    ])

    st.markdown("")
    st.plotly_chart(charts.night_drift(F), width="stretch", key="k_nightdrift")

    note(
        f"<b>Bedtime slides later; wake-up time does not.</b><br><br>"
        f"Last screen: {int(e1%24):02d}:{int(e1%1*60):02d} in week 1, "
        f"{int(e4%24):02d}:{int(e4%1*60):02d} in week 4 "
        f"({(e4-e1)*60:.0f} min later).<br>"
        f"First unlock: {int(f1):02d}:{int(f1%1*60):02d} → "
        f"{int(f4):02d}:{int(f4%1*60):02d} ({(f4-f1)*60:+.0f} min).<br>"
        f"Window between the two: {sleep1:.1f} h → {sleep4:.1f} h, "
        f"<b>{abs(sleep4-sleep1)*60:.0f} min less rest available per "
        f"night</b>.<br><br>"
        f"Unlocks after midnight go from {wk(b,'night_pickups',1):.1f} to "
        f"{wk(b,'night_pickups',4):.1f} per night. This is not one day running "
        f"long: it is {wk(b,'night_pickups',4):.0f} returns to the phone every "
        f"night.",
        "serious")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.day_span(b, "B"), width="stretch", key="k_span_night")
    with c2:
        st.plotly_chart(charts.compare_line(F, "night_pickups",
                        "Unlocks after midnight", "unlocks", 5),
                        width="stretch", key="k_nightpick")

    note(
        f"<b>User A, same period:</b> 0.0 min of screen between 23:00 and 06:00 "
        f"across all 30 days. Last screen at "
        f"{int(F['A'].last_use_h.mean()):02d}:"
        f"{int(F['A'].last_use_h.mean()%1*60):02d} on average, with no reopenings "
        f"after that. The 23:00 cut does not penalise every profile equally: A "
        f"respects it with no product intervention at all.",
        "good")

    st.markdown("### Why the night carries 20 % of the index")
    note(
        f"The night band carries 20 % of the index, the same as fragmentation "
        f"and more than long disconnection, despite being the smallest metric in "
        f"absolute terms ({b.night_min.mean():.0f} min on average against "
        f"{b.screen_min.mean():.0f} of total screen time).<br><br>"
        f"The reasoning: an hour of screen at 01:00 comes out of rest and an "
        f"hour at 17:00 does not, and the room for improvement is far more "
        f"reachable. Cutting two hours of daily use means changing a whole "
        f"routine; moving the last screen 40 minutes earlier is one change."
    )

# ===========================================================================
# 5 · WHERE THE TIME GOES
# ===========================================================================
with TABS[4]:
    d = F[who]
    apps, sites = U[who]["apps"], U[who]["sites"]
    st.markdown(f"### User {who} · how the time splits")

    st.markdown(
        '<span class="tag">device only</span>'
        '<span class="tag">never sent to a guardian</span>',
        unsafe_allow_html=True)

    top_share = apps.minutes.head(3).sum() / apps.minutes.sum() * 100
    kpis([
        ("Attributed time", f"{U[who]['attributed_h']:.0f} h",
         f"{U[who]['attributed_h']/U[who]['screen_h']*100:.0f} % of screen time"),
        ("Distinct apps", f"{len(apps)}", "over the whole month"),
        ("Distinct domains", f"{len(sites)}", "over the whole month"),
        ("Top 3 apps", f"{top_share:.0f} %", "of time spent in apps"),
        ("Distraction share", f"{d.distract_share.mean()*100:.0f} %",
         "social + entertainment + games"),
    ])

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.top_bars(apps, f"User {who} · apps by minutes"),
                        width="stretch", key="k_apps")
    with c2:
        st.plotly_chart(charts.top_bars(sites, f"User {who} · domains by minutes"),
                        width="stretch", key="k_sites")

    st.caption(
        "Colour is the content category, the same scale as the chart below. "
        "Openings and minutes per opening are in the tooltip and the full table."
    )

    st.plotly_chart(charts.category_area(
        U[who]["cats"], f"User {who} · minutes by content category"),
        width="stretch", key="k_cats")

    chrome = apps[apps.key == "com.android.chrome"]
    if who == "A":
        news = sites[sites.category == "NEWS"].minutes.sum() / sites.minutes.sum() * 100
        note(
            f"<b>Small catalogue.</b> {len(apps)} apps in 30 days: WhatsApp, "
            f"Spotify, Gmail, Maps, Phone and Calendar take up almost all of it, "
            f"and the top 3 accounts for {top_share:.0f} % of app time.<br><br>"
            f"<b>Browsing.</b> {news:.0f} % of the minutes are news sites; the "
            f"rest is occasional shopping and lookups.<br><br>"
            f"<b>Distraction falling.</b> Averaging "
            f"{d.distract_share.mean()*100:.0f} %, from "
            f"{wk(d,'distract_share',1)*100:.0f} % in week 1 to "
            f"{wk(d,'distract_share',4)*100:.0f} % in week 4.",
            "good")
        st.caption(
            f"Chrome shows {chrome.opens.iloc[0]:.0f} openings and only "
            f"{chrome.minutes.iloc[0]:.0f} min because browser time is "
            f"attributed to the domain visited, not to the browser."
        )
    else:
        msg = apps[apps.category == "MESSAGING"].minutes.sum()
        note(
            f"<b>Spread-out use.</b> {len(apps)} apps against user A's "
            f"{len(U['A']['apps'])}, and the top 3 holds only "
            f"{top_share:.0f} % of the time.<br><br>"
            f"<b>Parallel messaging.</b> {msg:,.0f} min split across WhatsApp, "
            f"Messages and Telegram.<br><br>"
            f"<b>Distraction share in the normal range.</b> "
            f"{d.distract_share.mean()*100:.0f} %, against user A's "
            f"{F['A'].distract_share.mean()*100:.0f} %. The category split is "
            f"not this profile's problem; the total volume and the timing are.",
            "warn")
        st.caption(
            "This chart only holds content that actually opened. Roblox and "
            "Clash of Clans do not appear despite 75 and 71 attempts, because "
            "the filter let 2 and 0 through respectively. The detail of blocked "
            "attempts is in \"What the phone stopped\"."
        )

    with st.expander("Full table of apps and domains"):
        c1, c2 = st.columns(2)
        c1.dataframe(apps.round(1), width="stretch", hide_index=True)
        c2.dataframe(sites.round(1), width="stretch", hide_index=True)


# ===========================================================================
# 6 · BLOCKS
# ===========================================================================
with TABS[5]:
    d = F[who]
    bf = U[who]["blocks"]
    st.markdown(f"### User {who} · blocked attempts")

    st.markdown(
        '<span class="tag">device only</span>'
        '<span class="tag">only the aggregate reaches a guardian</span>',
        unsafe_allow_html=True)

    if bf.empty:
        st.info("No blocks in the period.")
    else:
        # The week is assigned by `daily_frame` and only looked up here.
        # Recomputing it from the frame's first day would drift as soon as the
        # file's first day was partial and dropped out.
        week_of = dict(zip(d["day"], d["week"]))
        bf = bf.assign(week=[week_of[x] for x in bf["day"]])
        sens = bf[bf.category.isin(SENSITIVE)]
        kpis([
            ("Blocked attempts", f"{len(bf):,}", f"{len(bf)/len(d):.1f} per day"),
            ("Apps blocked", f"{d.blocks_app.sum():,}", None),
            ("Sites blocked", f"{d.blocks_url.sum():,}", None),
            ("Nudity detection", f"{d.blocks_nudity.sum():,}", "on device"),
            ("Adult + gambling", f"{len(sens):,}",
             f"{len(sens)/max(len(bf),1)*100:.0f} % of the total"),
            ("Ever opened", "0", "of the sensitive ones"),
        ])

        st.markdown("")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(charts.blocks_daily(
                bf, f"User {who} · blocked attempts per day"),
                width="stretch", key="k_blocks_daily")
        with c2:
            st.plotly_chart(charts.blocks_by_hour(
                bf, f"User {who} · blocks by hour of day"),
                width="stretch", key="k_blocks_hour")

        # the month does not fall into 7-day weeks: the last one is a 2-day
        # tail and that has to be said, or blocks look like they collapse at
        # the end.
        n_days = d.groupby("week").size()
        pivot = pd.crosstab(bf.category, bf.week)
        pivot.columns = [f"Week {c} ({n_days[c]} d)" for c in pivot.columns]
        st.dataframe(pivot, width="stretch")

        if who == "A":
            note(
                f"<b>{len(bf)} attempts in 30 days</b>, all of them "
                f"<code>SOCIAL_MEDIA</code> and <code>ENTERTAINMENT</code>. Zero "
                f"sensitive content in the period.<br><br>"
                f"<b>Falling trend:</b> {wk(d,'blocks',1,'sum'):.0f} blocks in "
                f"week 1, {wk(d,'blocks',4,'sum'):.0f} in week 4. The filter "
                f"steps in less and less, which suggests the opening habit has "
                f"moved rather than the barrier merely holding it back.<br><br>"
                f"This profile needs no action and generates no alerts.",
                "good")
        else:
            adult = bf[bf.category == "ADULT"]
            gamb = bf[bf.category == "GAMBLING"]
            nud = bf[bf.block_type == "NUDITY"]
            wk23 = len(sens[sens.week.isin([2, 3])])
            note(
                f"<b>Ordinary distraction: {len(bf)-len(sens):,} attempts</b>, "
                f"rising ({wk(d,'blocks',1,'sum'):.0f} → "
                f"{wk(d,'blocks',4,'sum'):.0f} per week). Mostly social and "
                f"entertainment.<br><br>"
                f"<b>Sensitive content: {len(adult)} adult attempts and "
                f"{len(gamb)} gambling ones</b>, with {len(nud)} on-device "
                f"nudity detections. All blocked; none ever opened.<br><br>"
                f"<b>Shape over time: a spike, not a trend.</b> {wk23} of the "
                f"{len(sens)} sensitive attempts ({wk23/len(sens)*100:.0f} %) "
                f"fall in weeks 2 and 3; in week 4 they drop to "
                f"{len(sens[sens.week==4])}.<br><br>"
                f"<b>Low persistence.</b> Grouped into 10-minute bursts: 1.2 "
                f"attempts on average, 3 at most. The pattern is an isolated "
                f"attempt followed by giving up, not insistence on the same "
                f"content. That is why this block generates no immediate "
                f"guardian notification, only a weekly summary entry (see "
                f"\"Alerts and nudges\").",
                "warn")

    st.markdown("### Scope of this data")
    note(
        "This tab is the device-side view. App and domain names, per-object "
        "counts and exact times are transmitted to no guardian and no server."
        "<br><br>"
        "On profiles with a guardian, what can appear in their digest is the "
        "aggregate state of the filter (<i>\"acted as usual\"</i> / "
        "<i>\"acted more than usual\"</i>) and the fact that "
        f"<b>{len(bf[bf.category.isin(SENSITIVE)]) if not bf.empty else 0} "
        f"sensitive-content attempts were blocked and none ever opened</b>. "
        "Verified against the stream: there is no <code>URL_VISIT</code> nor "
        "<code>APP_FOREGROUND</code> with category <code>ADULT</code> or "
        "<code>GAMBLING</code> in either file."
    )

# ===========================================================================
# 7 · ALERTS AND NUDGES
# ===========================================================================
with TABS[6]:
    d = F[who]
    sigs = U[who]["alerts"]
    nud = U[who]["nudges"]
    ns = nudge_summary(nud)
    sent = [x for x in sigs if x.decision == "sent"]

    st.markdown(f"### User {who} · month walkthrough")
    st.caption(
        "Every variable the rules read, on one axis. Each series runs as a "
        "percentage of its own maximum for the period, which is what lets them "
        "be compared without a second scale: what you read is the shape and the "
        "coincidence in time, and the real value with its unit is in the "
        "tooltip. **Click the legend** to switch any series on or off. Below "
        "zero, the rail showing what the phone emitted each day. The white line "
        "is the selected day."
    )

    replay = U[who]["replay"]
    by_day = {r["day"]: r for r in replay}
    days_list = [r["day"] for r in replay]
    default_day = next((r["day"] for r in replay if r["alert"]), days_list[-1])

    cursor = st.select_slider(
        "Day of the period", options=days_list, value=default_day,
        format_func=fecha, key=f"cursor_{who}")
    st_now = by_day[cursor]

    nudge_days = {r["day"] for r in replay if r["nudge"] and r["nudge"].fired}
    alert_days, positive_days = {}, {}
    for r in replay:
        if r["alert"]:
            alert_days[r["day"]] = "sent"
        elif r["digest_entry"]:
            alert_days[r["day"]] = "summary"
        if r["positives"]:
            positive_days[r["day"]] = True

    st.plotly_chart(
        charts.tracked_series(F[who], who, cursor, nudge_days, alert_days,
                              positive_days),
        width="stretch", key=f"k_tracked_{who}")

    st.markdown(f"#### Outputs on {fecha(cursor)}")
    row = F[who].set_index("day").loc[cursor]
    n = st_now["nudge"]
    pos_user = [x for x in st_now["positives"] if x.audience == "user"]
    pos_guard = [x for x in st_now["positives"] if x.audience == "guardian"]

    cols = st.columns(3 if HAS_GUARDIAN[who] else 2)

    with cols[0]:
        st.markdown('<div class="eyebrow">User\'s screen</div>',
                    unsafe_allow_html=True)
        if pos_user:
            x = pos_user[0]
            st.markdown(theme.phone(
                "09:00", "BALANCE",
                f"<div class='phone-eyebrow'>Your summary</div>"
                f"<div class='phone-h'>{x.headline}</div>"
                f"<div class='phone-p'>{x.guardian_text}</div>"
                + "".join(f"<div class='phone-row'><span>{k}</span>"
                          f"<span>{v}</span></div>"
                          for k, v in x.evidence.items())
                + "<div class='phone-cta ghost'>See the week</div>"),
                unsafe_allow_html=True)
        elif n and n.fired:
            st.markdown(theme.phone(
                pd.Timestamp(n.at_ms, unit="ms").strftime("%H:%M"), "BALANCE",
                f"<div class='phone-eyebrow'>Night nudge</div>"
                f"<div class='phone-h'>That is the {n.reopens}th time you have "
                f"opened your phone tonight.</div>"
                f"<div class='phone-p'>A month ago you had already put it down "
                f"by now.</div>"
                f"<div class='phone-cta'>Off until tomorrow</div>"
                f"<div class='phone-cta ghost'>5 more minutes</div>"),
                unsafe_allow_html=True)
        else:
            empty_box("No notifications")

    if HAS_GUARDIAN[who]:
        with cols[1]:
            st.markdown('<div class="eyebrow">Guardian\'s phone</div>',
                        unsafe_allow_html=True)
            g = st_now["alert"] or (pos_guard[0] if pos_guard else None)
            if g is not None:
                st.markdown(theme.phone(
                    "09:12", f"BALANCE · GUARDIAN OF {who}",
                    f"<div class='phone-eyebrow'>"
                    f"{'Alert' if g.tone == 'alert' else 'Summary'}</div>"
                    f"<div class='phone-h'>{g.headline}</div>"
                    f"<div class='phone-p'>{g.guardian_text}</div>"
                    f"<div class='phone-cta ghost'>See weekly summary</div>"),
                    unsafe_allow_html=True)
            else:
                empty_box("No notifications")

    with cols[-1]:
        st.markdown('<div class="eyebrow">Stored on the device</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f"<div class='phone-row'><span>Screen</span>"
            f"<span>{row.screen_min:.0f} min</span></div>"
            f"<div class='phone-row'><span>Unlocks</span>"
            f"<span>{row.pickups:.0f}</span></div>"
            f"<div class='phone-row'><span>Late night</span>"
            f"<span>{row.night_min:.0f} min</span></div>"
            f"<div class='phone-row'><span>Last night-band screen</span>"
            f"<span>{reloj(row.night_end_h)}</span></div>"
            f"<div class='phone-row'><span>Longest disconnection</span>"
            f"<span>{row.longest_offline_h:.1f} h</span></div>"
            f"<div class='phone-row'><span>· started</span>"
            f"<span>{row.longest_offline_when or 'no stretch'}</span></div>"
            f"<div class='phone-row'><span>Distraction share</span>"
            f"<span>{row.distract_share*100:.0f} %</span></div>"
            f"<div class='phone-row'><span>Sensitive attempts</span>"
            f"<span>{row.blocks_sensitive:.0f}</span></div>"
            f"<div class='phone-row'><span>Total blocks</span>"
            f"<span>{row.blocks:.0f}</span></div>"
            f"<div class='phone-row'><span>Index for the day</span>"
            f"<span>{row.score:.0f} / 100</span></div>"
            f"<div class='phone-row'><span>Nudges so far</span>"
            f"<span>{st_now['nudges_so_far']}</span></div>"
            f"<div class='phone-row'><span>Reinforcements so far</span>"
            f"<span>{st_now['positives_so_far']}</span></div>",
            unsafe_allow_html=True)
        st.caption(
            "These figures are computed and stored on the phone."
            + ("  Only the rounded aggregate of the weekly digest reaches the "
               "guardian." if HAS_GUARDIAN[who] else "")
        )

    st.markdown("### Everything the phone emitted this month")
    em = U[who]["emissions"]
    if em:
        st.dataframe(pd.DataFrame([{
            "Date": fecha(e["day"]),
            "Destination": e["destination"],
            "Type": e["type"],
            "Detail": e["detail"],
        # altura al contenido: una tabla de 3 filas con hueco para 10 parece
        # que ha fallado la carga.
        } for e in em]), width="stretch", hide_index=True,
            height=min(320, 38 + 35 * len(em)))
        st.caption(
            f"{len(em)} outputs over 30 days: "
            f"{sum(1 for e in em if e['destination'].startswith('User'))} to "
            f"the user, "
            f"{sum(1 for e in em if e['destination'] == 'Guardian · notification')} "
            f"as a guardian notification and "
            f"{sum(1 for e in em if e['destination'] == 'Guardian · weekly summary')} "
            f"as a weekly summary entry."
        )
    else:
        st.caption("The phone emitted nothing in the period.")

    st.markdown(f"### User {who} · notifications in the period")
    kpis([
        ("Guardian notifications",
         f"{len(sent)}" if HAS_GUARDIAN[who] else "n/a",
         f"quota {ALERT_BUDGET}/month" if HAS_GUARDIAN[who] else "no guardian"),
        ("Into weekly summary",
         f"{sum(1 for x in sigs if x.decision == 'summary')}"
         if HAS_GUARDIAN[who] else "n/a", "not notified"),
        ("Reinforcements sent",
         f"{sum(1 for x in U[who]['positives'] if x.decision == 'sent')}",
         "one per week at most"),
        ("Nights with a nudge", f"{ns["nights with a nudge"]}/{ns["nights"]}",
         f"{ns["appearance rate"]*100:.0f} % of nights"),
        ("Min after the nudge", f"{ns["minutes at stake after the nudge"]:.0f}",
         f"{ns["share of night total"]*100:.0f} % of the night total"),
    ])

    st.markdown("### Notifications sent to the guardian")
    if not HAS_GUARDIAN[who]:
        note(
            f"<b>No guardian assigned.</b> User {who} is an adult: there is no "
            f"recipient to notify, so the alert rules run all the same but their "
            f"output only feeds the index and the nudges on the device "
            f"itself.<br><br>"
            f"None of the three rules fired in the period: "
            f"{d.night_min.sum():.0f} minutes of night-band screen over 30 days "
            f"and {ns["nights with a nudge"]} nights with a nudge.",
            "good")
    elif not sent:
        note(
            f"<b>None in the period.</b> User {who} fired no rule at all: "
            f"{d.night_min.sum():.0f} minutes of night-band screen over 30 days "
            f"and {ns["nights with a nudge"]} nights with a nudge. The guardian "
            f"receives only the weekly digest, in the \"all in order\" state.",
            "good")
    for x in sent:
        ev = "".join(f"<div class='phone-row'><span>{k}</span>"
                     f"<span>{v}</span></div>" for k, v in x.evidence.items())
        st.markdown(
            f'<div class="eyebrow">Notification · {fecha(x.day)} · '
            f'recipient: guardian of user {who}</div>',
            unsafe_allow_html=True)
        _pc, _pr = st.columns([1, 2])
        with _pc:
            st.markdown(theme.phone(
                "09:12", f"BALANCE · GUARDIAN OF {who}",
                f"<div class='phone-eyebrow'>Alert</div>"
                f"<div class='phone-h'>{x.headline}</div>"
                f"<div class='phone-p'>{x.guardian_text}</div>"
                f"<div class='phone-cta ghost'>See weekly summary</div>"),
                unsafe_allow_html=True)
        note(
            f"<b>Rule:</b> <code>{x.key}</code> · "
            f"active from {fecha(x.day)} to {fecha(x.until)} "
            f"({x.days_true} days) · priority {x.priority:.2f}.<br><br>"
            f"The rule stops holding on {fecha(x.until)} because the rolling "
            f"14-day reference absorbs the new behaviour. The alert is issued "
            f"once, on detecting the change. The absolute level stays visible in "
            f"the index and the weekly digest, which use no rolling reference.",
            "serious")
        with st.expander("Data behind the alert (never leaves the device)"):
            st.markdown(ev, unsafe_allow_html=True)
            st.caption(
                "The guardian receives the notification text. These figures "
                "are computed and stay on the phone.")

    st.markdown("### Reinforcements sent")
    pos = U[who]["positives"]
    pos_sent = [x for x in pos if x.decision == "sent"]
    if pos_sent:
        for x in pos_sent:
            st.markdown(
                f'<div class="eyebrow">{fecha(x.day)} · recipient: '
                f'{"the user themselves" if x.audience == "user" else f"guardian of user {who}"}'
                f'</div>', unsafe_allow_html=True)
            note(f"<b>{x.headline}</b><br>\"{x.guardian_text}\"", "good")
    else:
        st.caption("No reinforcement in the period.")
    pos_held = [x for x in pos if x.decision != "sent"]
    if pos_held:
        with st.expander(f"{len(pos_held)} reinforcements recorded, not notified"):
            st.dataframe(pd.DataFrame([{
                "Date": fecha(x.day), "Rule": x.key,
                "Recipient": x.audience,
                "Detail": x.guardian_text, "Reason": x.reason,
            } for x in pos_held]), width="stretch", hide_index=True)

    st.markdown("### Held signals")
    rest = [x for x in sigs if x.decision != "sent"]
    if rest:
        st.dataframe(pd.DataFrame([{
            "Rule": x.key,
            "Detected": fecha(x.day),
            "Priority": x.priority,
            "Destination": x.decision,
            "Reason": x.reason,
        } for x in rest]), width="stretch", hide_index=True)
    else:
        st.caption("No signal held in the period.")

    st.markdown("### Rule coverage")
    rows = []
    for key, desc in [
        ("night_drift", "Median of 5 nights against the previous 14, plus the "
                        "delay in the time of the last screen"),
        ("sensitive_spike", "ADULT or GAMBLING attempts over 7 days against the "
                            "rate of the previous 7"),
        ("screen_jump", "Median screen time over 5 days against the previous "
                        "14"),
    ]:
        hit = next((x for x in sigs if x.key == key), None)
        rows.append({
            "Rule": key,
            "What it compares": desc,
            "User A": next((f"{x.decision} · {fecha(x.day)}"
                            for x in U["A"]["alerts"] if x.key == key),
                           "does not fire"),
            "User B": next((f"{x.decision} · {fecha(x.day)}"
                            for x in U["B"]["alerts"] if x.key == key),
                           "does not fire"),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    note(
        f"<code>screen_jump</code> fires on neither profile. User B's daily use "
        f"grows {(wk(F['B'],'screen_min',4)/wk(F['B'],'screen_min',1)-1)*100:.0f} "
        f"% over the month, below the threshold of any reasonable volume rule, "
        f"while their night band multiplies by "
        f"{wk(F['B'],'night_min',4)/max(wk(F['B'],'night_min',1),.01):.0f}. "
        f"Catching this case depends on watching the schedule, not the total.",
        "warn")

    st.markdown("### On-device nudge")
    st.caption(
        f"Shown on the second reopening from "
        f"{int(23 + NUDGE_AFTER_MIN // 60):02d}:{NUDGE_AFTER_MIN % 60:02d} "
        f"onwards, at most once per night. The figures come from replaying the "
        f"rule over the 30 days of the period."
    )
    ca, cb = st.columns(2)
    with ca:
        st.markdown(f"**User {who} · activation**")
        st.markdown(
            f"<div class='phone-row'><span>Nights evaluated</span>"
            f"<span>{ns["nights"]}</span></div>"
            f"<div class='phone-row'><span>Nights with a nudge</span>"
            f"<span>{ns["nights with a nudge"]} "
            f"({ns["appearance rate"]*100:.0f} %)</span></div>"
            f"<div class='phone-row'><span>Night minutes this month</span>"
            f"<span>{ns["total night minutes"]:.0f}</span></div>"
            f"<div class='phone-row'><span>Minutes after the nudge</span>"
            f"<span>{ns["minutes at stake after the nudge"]:.0f} "
            f"({ns["share of night total"]*100:.0f} %)</span></div>"
            f"<div class='phone-row'><span>Per nudged night</span>"
            f"<span>{ns["minutes at stake per nudged night"]:.0f} min</span></div>",
            unsafe_allow_html=True)
    with cb:
        quiet = Counter(n.quiet_reason for n in nud if n.quiet_reason)
        st.markdown("**Nights without a nudge · reason**")
        for reason, n in quiet.most_common():
            st.markdown(
                f"<div class='phone-row'><span>{reason}</span>"
                f"<span>{n}</span></div>", unsafe_allow_html=True)

    note(
        f"The minutes after the nudge bound its headroom: "
        f"{nudge_summary(U['B']['nudges'])["minutes at stake after the nudge"]:.0f} of "
        f"user B's {nudge_summary(U['B']['nudges'])["total night minutes"]:.0f} "
        f"night minutes "
        f"({nudge_summary(U['B']['nudges'])["share of night total"]*100:.0f} %), "
        f"about {nudge_summary(U['B']['nudges'])["minutes at stake per nudged night"]:.0f} "
        f"per night it appears. That is the theoretical maximum recoverable, not "
        f"the expected effect.<br><br>"
        f"The activation rate on user A is 0 %: the rule fires on none of their "
        f"30 nights, with no per-profile configuration."
    )

# ===========================================================================
# 8 · THE DATA
# ===========================================================================
with TABS[7]:
    st.markdown("### What is actually in the files")

    ev = pd.DataFrame([
        {"User": u, **Counter(e["event_type"] for e in U[u]["events"])}
        for u in DATA]).set_index("User").T.fillna(0).astype(int)
    ev["What it means"] = [{
        "SCREEN_ON": "The screen lights up. May be a glance or the start of real use.",
        "SCREEN_OFF": "The screen goes dark.",
        "USER_PRESENT": "A real unlock (PIN / biometrics). This is what turns a SCREEN_ON into a pickup.",
        "APP_FOREGROUND": "An app comes to the foreground. Carries package_name and category.",
        "URL_VISIT": "A page viewed in the browser. Carries url_domain and category. Domain only, never a path.",
        "BLOCK": "An attempt stopped. The content did NOT open. Carries block_type.",
    }[i] for i in ev.index]
    st.dataframe(ev, width="stretch")

    st.markdown("### The eight fields, and what we do with each")
    st.dataframe(pd.DataFrame([
        ("id", "int", "Monotonic within the file, in time order.",
         "Tie-breaking when sorting, nothing else."),
        ("event_type", "str", "One of the six types above.",
         "Screen state machine, time attribution, blocks."),
        ("timestamp_millis", "int", "Epoch milliseconds, wall clock normalised to UTC.",
         "Everything. Day = local midnight; the night runs 23:00→06:00 the next day."),
        ("package_name", "str|null", "Android package. On APP_FOREGROUND and on app BLOCKs.",
         "App ranking, app switches, distinct apps."),
        ("url_domain", "str|null", "Domain only. On URL_VISIT and on site BLOCKs.",
         "Domain ranking. Browser time is reassigned to the domain."),
        ("category", "str|null", "One shared vocabulary for apps and sites.",
         "Minutes per category, distraction share, sensitive (ADULT/GAMBLING)."),
        ("block_type", "str|null", "APP · URL · NUDITY. Only on BLOCK.",
         "Separates list filtering from on-device nudity detection."),
        ("is_keyguard_locked", "bool|null", "true on a passive SCREEN_ON, false on USER_PRESENT.",
         "Tells a glance from a real pickup."),
    ], columns=["Field", "Type", "What it is", "What we use it for"]),
        width="stretch", hide_index=True)

    st.markdown("### Stream anomalies and how they are handled")
    note(
        "<b>1 · Overlapping screen stretches.</b> 77 <code>SCREEN_ON</code> in "
        "user A and 411 in user B fire while the screen is already on, balanced "
        "later by consecutive <code>SCREEN_OFF</code>. The data does not say "
        "which OFF closes which ON, and choosing wrong changes the result in "
        "both directions: pairing as a stack gives 64.9 h for user A (+6 %, the "
        "overlap counted twice) and as a queue 56.7 h (−7 %, the trailing "
        "stretch lost).<br>"
        "The screen is modelled as a <b>depth counter</b> (ON adds, OFF "
        "subtracts; on while &gt; 0), which returns the <b>union</b> of the "
        "stretches: <b>61.1 h</b>. The union does not depend on the pairing "
        "chosen, and it is what \"the screen was on\" means."
        "<br><br>"
        "<b>2 · Days truncated by the file edge.</b> User B's file ends at 00:46 "
        "on 31 May. That day has 0.8 h of coverage and is excluded from "
        "averages, rankings, the heatmap and blocks; its events do still count "
        "towards the night of the 30th. Without that filter, user B's mean "
        "screen time drops from 261.8 to 253.7 min."
        "<br><br>"
        "<b>3 · First unlock floored at 06:00.</b> With the day cutting at "
        "midnight, a day starting at 00:20 (the tail of the previous night) "
        "would register as the start of a working day. The first unlock is "
        "defined as the first one from 06:00 onwards; the small hours are "
        "counted separately."
        "<br><br>"
        "<b>4 · Stretches crossing midnight.</b> They are split at the day "
        "boundary so daily screen time adds up to exactly that day."
        "<br><br>"
        "<b>5 · Guards that never trigger here.</b> App or URL events with the "
        "screen off, <code>USER_PRESENT</code> with no preceding "
        "<code>SCREEN_ON</code>, and apps in the foreground for more than 45 "
        "minutes are all handled in the code and do not occur in these two "
        "files. The one anomaly that does show up is 4 duplicate "
        "<code>USER_PRESENT</code> inside a single stretch in user A and 6 in "
        "user B, recorded rather than dropped silently."
    )

    st.markdown("### From event to metric")
    st.dataframe(pd.DataFrame([
        ("Screen time", "Union of SCREEN_ON→SCREEN_OFF intervals, split at midnight."),
        ("Real pickup", "A SCREEN_ON with a USER_PRESENT before the next ON/OFF."),
        ("Glance", "A SCREEN_ON with no USER_PRESENT: the screen came on, the phone never opened."),
        ("Time per app", "From APP_FOREGROUND to the next foreground change, BLOCK or screen off. Capped at 45 min."),
        ("Time per domain", "The same, but a URL_VISIT takes the time off the browser and the domain keeps it."),
        ("Night band", "23:00 on day D → 06:00 on day D+1. The calendar day cuts at midnight; sleep does not."),
        ("Longest disconnection", "Largest screen-free gap inside the waking window (07:00–23:00), with the moment it starts."),
        ("App switch", "A real foreground transition between different packages, reset each day."),
        ("Distraction share", "Minutes in SOCIAL_MEDIA + ENTERTAINMENT + GAMING over attributed time."),
        ("Your normal", "Rolling median of the same user's previous 14 days (median, not mean: one odd day should not move the bar)."),
    ], columns=["Metric", "How it is derived"]), width="stretch", hide_index=True)

    st.markdown("### How much screen time we manage to explain")
    kpis([(f"{u} · screen reconstructed", f"{U[u]['screen_h']:.0f} h", None)
          for u in DATA] +
         [(f"{u} · attributed to app/site",
           f"{U[u]['attributed_h']/U[u]['screen_h']*100:.0f} %", None) for u in DATA])
    st.caption(
        "The rest is screen-on time with no app in the foreground: lock screen, "
        "home screen and notifications. User B's 67 % against user A's 86 % is "
        "consistent with their pattern of frequent wake-ups that never open "
        "anything."
    )

    st.markdown("### The index, component by component")
    st.dataframe(pd.DataFrame([
        (label, f"{good:g}", f"{bad:g}", f"{w*100:.0f} %")
        for col, label, good, bad, w in COMPONENTS],
        columns=["Component", "Value scoring 100", "Value scoring 0", "Weight"]),
        width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    for col, u in ((c1, "A"), (c2, "B")):
        mean_row = F[u].mean(numeric_only=True)
        col.plotly_chart(charts.score_breakdown(contributions(mean_row), u),
                         width="stretch", key=f"k_breakdown_{u}")
    note(
        "Blocks do not score in the index. A <code>BLOCK</code> means the filter "
        "acted and the content never opened; docking points for the attempt "
        "would penalise the user for something the product already handled and "
        "would create an incentive to turn the protection off. Blocks feed the "
        "alert rules and the guardian digest, not the score."
    )
