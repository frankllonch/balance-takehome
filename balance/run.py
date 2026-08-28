"""
CLI: the same engine as the dashboard, without the dashboard.

    python -m balance.run                    # both profiles, text
    python -m balance.run --user B           # B only
    python -m balance.run --format json      # to pipe into jq
    python -m balance.run --csv out/         # daily and weekly frames

It exists for two reasons. The first is verification: if the only place the
results can be seen is a user interface, there is no way to tell an engine that
computes from a screen with hand-written numbers. The second is operational:
this is the natural entry point for a nightly cron or an ingestion job, without
dragging Streamlit along as a dependency.

No compute layer in `balance/` imports Streamlit or Plotly, so this module runs
on pandas and little else.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path

from .events import load
from .intelligence import (
    emissions, evaluate_alerts, evaluate_positives, guardian_digest,
    month_replay, nudge_summary, replay_nudge,
)
from .metrics import blocks_frame, daily_frame, totals, weekly_frame
from .score import add_score

#: Input files and whether the profile has a guardian assigned. In production
#: this would come from the account, not from a constant.
PROFILES = {
    "A": {"path": "data/events_user_a.json", "guardian": False},
    "B": {"path": "data/events_user_b.json", "guardian": True},
}


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------

def analyse(user: str, root: Path) -> dict:
    """Everything the system derives from one event file.

    It is a pure function of the log: same file, same result, no external state
    and no dependency on the time of execution.
    """
    cfg = PROFILES[user]
    tl = load(root / cfg["path"], user)
    df = add_score(daily_frame(tl))
    days = set(df["day"])

    nudges = replay_nudge(tl, df)
    alerts = evaluate_alerts(df)
    positives = evaluate_positives(df, cfg["guardian"])
    replay = month_replay(df, nudges, positives)

    return {
        "user": user,
        "has_guardian": cfg["guardian"],
        "timeline": tl,
        "daily": df,
        "weekly": weekly_frame(df),
        "apps": totals(tl, df, "app"),
        "sites": totals(tl, df, "site"),
        "blocks": blocks_frame(tl, days),
        "alerts": alerts,
        "positives": positives,
        "nudges": nudges,
        "nudge_summary": nudge_summary(nudges),
        "digest": guardian_digest(df, alerts),
        "emissions": emissions(replay),
    }


# ---------------------------------------------------------------------------
# Text output
# ---------------------------------------------------------------------------

def _rule(title: str = "", width: int = 76) -> str:
    if not title:
        return "─" * width
    return f"── {title} " + "─" * max(0, width - len(title) - 4)


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h{m:02d}" if h else f"{m}min"


def render_text(r: dict) -> str:
    df, w = r["daily"], r["weekly"]
    tl = r["timeline"]
    out: list[str] = []
    add = out.append

    add(_rule(f"PROFILE {r['user']}"))
    add(f"  {len(tl.events):,} events · {len(df)} complete days "
        f"· {len(tl.intervals)} screen stretches")
    add(f"  guardian assigned: {'yes' if r['has_guardian'] else 'no'}")
    if tl.anomalies:
        for k, v in tl.anomalies.items():
            add(f"  anomaly: {k} ×{v}")
    add("")

    add(_rule("PERIOD AVERAGES"))
    for label, value in [
        ("screen time per day", _hm(df.screen_min.mean())),
        ("offline while awake", f"{df.offline_wake_h.mean():.1f} h"),
        ("real unlocks", f"{df.pickups.mean():.1f}"),
        ("glances without opening", f"{df.glances.mean():.1f}"),
        ("late-night minutes", f"{df.night_min.mean():.1f} min"),
        ("longest disconnection", f"{df.longest_offline_s.mean()/3600:.1f} h"),
        ("best stretch of the period",
         f"{df.longest_offline_h.max():.1f} h on "
         f"{df.loc[df.longest_offline_h.idxmax(), 'longest_offline_when']}"),
        ("distinct apps", f"{df.distinct_apps.mean():.1f}"),
        ("app switches per hour", f"{df.switches_per_screen_hour.mean():.1f}"),
        ("distraction share", f"{df.distract_share.mean()*100:.1f} %"),
        ("blocks per day", f"{df.blocks.mean():.1f}"),
        ("sensitive attempts (total)", f"{int(df.blocks_sensitive.sum())}"),
        ("wellbeing index", f"{df.score.mean():.1f} / 100"),
    ]:
        add(f"  {label:<28} {value:>12}")
    add("")

    add(_rule("BY WEEK"))
    add(f"  {'wk':<5}{'days':>5}{'screen':>10}{'unlocks':>9}"
        f"{'night':>8}{'blk/d':>8}{'index':>8}")
    for i, row in w.iterrows():
        marca = " *" if row["is_partial"] else "  "
        add(f"  W{i:<4}{int(row['days']):>5}{row['screen_min']:>9.0f}m"
            f"{row['pickups']:>9.0f}{row['night_min']:>7.0f}m"
            f"{row['blocks']:>8.1f}{row['score']:>8.0f}{marca}")
    add("  * short week: generates no reinforcements and enters no comparisons")
    add("")

    add(_rule("GUARDIAN ALERTS"))
    if not r["has_guardian"]:
        add("  profile with no guardian: rules run, there is no recipient")
    elif not r["alerts"]:
        add("  no rule fired in the period")
    for s in r["alerts"]:
        add(f"  [{s.decision:<10}] {s.day}  {s.key}  priority {s.priority:.2f}")
        add(f"               {s.headline}")
        if s.decision == "sent":
            add(f"               \"{s.guardian_text}\"")
            add(f"               active {s.days_true} days, until {s.until}")
        else:
            add(f"               reason: {s.reason}")
    add("")

    add(_rule("REINFORCEMENTS"))
    if not r["positives"]:
        add("  none in the period")
    for s in r["positives"]:
        dest = "user" if s.audience == "user" else "guardian"
        add(f"  [{s.decision:<10}] {s.day}  {s.key} → {dest}")
        add(f"               \"{s.guardian_text}\"")
    add("")

    add(_rule("NIGHT NUDGE (replayed over history)"))
    ns = r["nudge_summary"]
    add(f"  nights evaluated            {ns['nights']:>12}")
    add(f"  nights with a nudge         "
        f"{ns['nights with a nudge']:>7} ({ns['appearance rate']*100:.0f} %)")
    add(f"  night minutes in period     {ns['total night minutes']:>12.0f}")
    add(f"  minutes after the nudge     "
        f"{ns['minutes at stake after the nudge']:>7.0f} "
        f"({ns['share of night total']*100:.0f} %)")
    add(f"  per nudged night            "
        f"{ns['minutes at stake per nudged night']:>9.0f} min")
    add("")

    add(_rule("DIGEST THAT WOULD LEAVE THE DEVICE"))
    if r["has_guardian"]:
        for k, v in r["digest"].items():
            add(f"  {k:<34} {v:>24}")
    else:
        add("  profile with no guardian: nothing leaves the device")
    add("")

    add(_rule("EMISSIONS IN THE PERIOD"))
    em = r["emissions"]
    if not em:
        add("  the phone emitted nothing")
    for e in em:
        add(f"  {e['day']}  {e['destination']:<26} {e['detail'][:42]}")
    add(f"  total: {len(em)} outputs over {len(df)} days")
    add("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def _plain(obj):
    """Converts to serialisable types without losing precision on the way."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_plain(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "item"):          # numpy scalars
        return obj.item()
    return obj


def render_json(r: dict) -> dict:
    df, w = r["daily"], r["weekly"]
    return _plain({
        "user": r["user"],
        "has_guardian": r["has_guardian"],
        "days": len(df),
        "anomalies": dict(r["timeline"].anomalies),
        "averages": {
            "screen_min": df.screen_min.mean(),
            "offline_wake_h": df.offline_wake_h.mean(),
            "pickups": df.pickups.mean(),
            "glances": df.glances.mean(),
            "night_min": df.night_min.mean(),
            "longest_offline_h": df.longest_offline_s.mean() / 3600,
            "best_offline_h": df.longest_offline_h.max(),
            "best_offline_when": df.loc[df.longest_offline_h.idxmax(),
                                        "longest_offline_when"],
            "distinct_apps": df.distinct_apps.mean(),
            "distract_share": df.distract_share.mean(),
            "blocks": df.blocks.mean(),
            "score": df.score.mean(),
        },
        "weekly": [
            {"week": int(i), "days": int(row["days"]),
             "screen_min": row["screen_min"], "pickups": row["pickups"],
             "night_min": row["night_min"], "blocks": row["blocks"],
             "score": row["score"], "is_partial": bool(row["is_partial"])}
            for i, row in w.iterrows()
        ],
        "alerts": [
            {"key": s.key, "day": s.day, "until": s.until,
             "decision": s.decision, "priority": s.priority,
             "audience": s.audience, "tone": s.tone,
             "headline": s.headline, "text": s.guardian_text,
             "reason": s.reason, "evidence": s.evidence}
            for s in r["alerts"]
        ],
        "positives": [
            {"key": s.key, "day": s.day, "decision": s.decision,
             "audience": s.audience, "headline": s.headline,
             "text": s.guardian_text, "evidence": s.evidence}
            for s in r["positives"]
        ],
        "nudge": r["nudge_summary"],
        "guardian_digest": r["digest"] if r["has_guardian"] else None,
        "emissions": r["emissions"],
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m balance.run",
        description="Derives metrics, index, alerts and nudges from a device "
                    "event log.")
    ap.add_argument("--user", choices=[*PROFILES, "all"], default="all",
                    help="profile to analyse (all of them by default)")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--csv", metavar="DIR", type=Path,
                    help="also dump the daily and weekly frames to CSV")
    ap.add_argument("--root", type=Path, default=Path.cwd(),
                    help="directory containing data/ (the current one by default)")
    args = ap.parse_args(argv)

    users = list(PROFILES) if args.user == "all" else [args.user]
    results = []
    for u in users:
        r = analyse(u, args.root)
        results.append(r)
        if args.csv:
            args.csv.mkdir(parents=True, exist_ok=True)
            # columns holding dictionaries do not go into a flat CSV
            r["daily"].drop(columns=["_cat_s", "_app_s", "_site_s"]).to_csv(
                args.csv / f"daily_{u}.csv", index=False)
            r["weekly"].to_csv(args.csv / f"weekly_{u}.csv")

    if args.format == "json":
        print(json.dumps([render_json(r) for r in results],
                         ensure_ascii=False, indent=2))
    else:
        print("\n".join(render_text(r) for r in results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
