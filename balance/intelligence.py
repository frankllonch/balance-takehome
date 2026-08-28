"""
Layer 3 · from metric to decision: what gets surfaced, to whom, and what stays
quiet.

Two deliberately asymmetric surfaces:

* **Guardian alerts.** Coarse, object-free, on a budget. The real failure mode
  of a notification channel aimed at a parent is not missing an event: it is
  shouting until they stop reading. Hence a **silence budget**
  (`ALERT_BUDGET`): every candidate has to earn its slot, and whatever does not
  fit drops to the weekly summary. Discarded candidates are kept with their
  reason, because the interesting part of an alerting system is the negatives.

* **User nudges.** On device, with detail, and with their own silence rules. A
  nudge that always shows stops being a nudge.

Everything here is evaluable backwards over historical data, which is how you
measure whether a rule is worth anything before sending it to anyone
(`replay_nudge`).

One limitation worth stating out loud: the drift detector uses a rolling
reference, so it **stops firing once the new behaviour becomes the normal one**.
For alerting that is correct (you report the change, once, not every day); but
it means the detector going quiet does not mean "fixed". The absolute level is
still carried by the index and the weekly summary, which have no short memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .events import Timeline, to_dt
from .metrics import _night_window

# ---------------------------------------------------------------------------
# Rule parameters (in one place, so they can be argued about)
# ---------------------------------------------------------------------------

#: Windows for the night-drift detector. 5 recent nights against the previous
#: 14: needs 19 days of history, and in exchange fires early without reacting
#: to a single odd night.
DRIFT_RECENT, DRIFT_BASE = 5, 14
DRIFT_RATIO = 2.0          # the recent median doubles the reference one
DRIFT_ABS_MIN = 20.0       # ...and it is at least 20 min: 2× of 3 min is nothing
DRIFT_CLOCK_MIN = 40.0     # ...and lights-out has moved 40 min or more

#: Sensitive-content spike: 7-day sum against the rate of the previous ones.
SPIKE_RECENT, SPIKE_BASE = 7, 7
SPIKE_RATIO, SPIKE_ABS_MIN = 2.5, 10

#: The "obvious" rule almost anyone would implement, included on purpose so we
#: can show it does NOT fire on this data.
SCREEN_JUMP_RATIO, SCREEN_JUMP_ABS = 1.4, 60.0

#: Guardian alert quota per 30 days, and minimum gap between two.
ALERT_BUDGET = 2
ALERT_MIN_GAP_DAYS = 10

#: Night nudge: arms 30 min after the band opens, and only from the second
#: reopening onwards.
NUDGE_AFTER_MIN = 30
NUDGE_MIN_REOPENS = 2


# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """A candidate alert. It may end up sent, summarised or discarded."""
    key: str
    day: date                   # first day the rule holds
    headline: str
    guardian_text: str          # the exact wording a guardian would read
    magnitude: float            # 0 to 1 · how far outside normal
    persistence: float          # 0 to 1 · how long it has been outside
    actionability: float        # 0 to 1 · can the guardian do anything with it?
    evidence: dict = field(default_factory=dict)   # NEVER leaves the device
    decision: str = "candidate"                    # sent | summary | discarded
    reason: str = ""
    until: date | None = None   # last day of the episode, if it runs on
    audience: str = "guardian"  # guardian | user
    tone: str = "alert"         # alert | reinforcement

    @property
    def days_true(self) -> int:
        return ((self.until - self.day).days + 1) if self.until else 1

    @property
    def priority(self) -> float:
        """Product, not sum: an alert that is huge but one day long, or
        persistent but not actionable, should not sneak through."""
        return round(self.magnitude * self.persistence * self.actionability, 3)


@dataclass
class NightNudge:
    """What the nudge would have done each night, and what was at stake."""
    day: date
    fired: bool
    at_ms: int | None
    quiet_reason: str
    reopens: int
    minutes_after: float        # night screen time after the trigger
    night_minutes: float


def _clamp(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


# ---------------------------------------------------------------------------
# Rules · guardian
# ---------------------------------------------------------------------------

def _night_drift(df: pd.DataFrame) -> list[Signal]:
    """A regime change in the night band.

    Not a threshold ("more than 30 min after midnight"), a sustained shift in
    distribution. With a threshold, B would have fired and stopped firing
    night by night; and above all, a fixed threshold cannot tell someone who
    has always been like this from someone who **has just changed**. The
    second is the only one worth interrupting a parent for.
    """
    out: list[Signal] = []
    need = DRIFT_RECENT + DRIFT_BASE
    for i in range(need - 1, len(df)):
        rec = df.night_min.iloc[i - DRIFT_RECENT + 1: i + 1]
        base = df.night_min.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE: i - DRIFT_RECENT + 1]
        rec_m, base_m = rec.median(), max(base.median(), 1.0)
        clock = (df.night_end_h.iloc[i - DRIFT_RECENT + 1: i + 1].median()
                 - df.night_end_h.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE:
                                       i - DRIFT_RECENT + 1].median()) * 60
        above = int((rec > base_m).sum())

        if not (rec_m >= DRIFT_ABS_MIN and rec_m >= DRIFT_RATIO * base_m
                and clock >= DRIFT_CLOCK_MIN and above >= DRIFT_RECENT - 1):
            continue

        out.append(Signal(
            key="night_drift",
            day=df.day.iloc[i],
            headline="The sleep schedule has shifted",
            # Purely descriptive. No recommendations: the product reports a
            # measured change, it does not tell anyone what to do about it.
            guardian_text=(
                # Wording note: this avoids the words "other" and "news",
                # which collide with the OTHER and NEWS category names and
                # would trip the privacy test for no real reason.
                "Over the last few weeks the phone has been going dark later "
                "than it used to, and the wake-up time has not changed. The "
                "remaining indicators are holding steady."),
            magnitude=_clamp((rec_m / base_m - DRIFT_RATIO) / 4 + .5),
            persistence=_clamp(above / DRIFT_RECENT),
            actionability=1.0,      # a schedule is exactly what a guardian can negotiate
            evidence={
                "recent night median (min)": round(float(rec_m), 1),
                "reference night median (min)": round(float(base.median()), 1),
                "last-screen delay (min)": int(round(clock)),
                "nights above normal": f"{above} of {DRIFT_RECENT}",
            },
        ))
    return out


def _sensitive_spike(df: pd.DataFrame) -> list[Signal]:
    """An uptick in attempts towards adult or gambling content.

    It is detected, but almost never sent: see `_decide`. The phone already
    blocked it, so urgency is low and the cost of telling a parent in the heat
    of the moment is high.
    """
    out: list[Signal] = []
    need = SPIKE_RECENT + SPIKE_BASE
    for i in range(need - 1, len(df)):
        rec = df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1: i + 1].sum()
        base_rate = (df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1 - SPIKE_BASE:
                                              i - SPIKE_RECENT + 1].sum()
                     / SPIKE_BASE * SPIKE_RECENT)
        if not (rec >= SPIKE_ABS_MIN and rec >= SPIKE_RATIO * max(base_rate, 1)):
            continue
        out.append(Signal(
            key="sensitive_spike",
            day=df.day.iloc[i],
            headline="The sensitive-content filter acted more than usual",
            guardian_text=(
                "This week the content filter stepped in more often than usual. "
                "Every attempt was blocked and no content opened."),
            magnitude=_clamp((rec / max(base_rate, 1) - SPIKE_RATIO) / 5 + .5),
            persistence=_clamp(
                (df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1: i + 1] > 0).sum()
                / SPIKE_RECENT),
            # Deliberately low: the block already happened. What is left is a
            # conversation, and that conversation gains nothing by arriving
            # today rather than on Sunday.
            actionability=0.35,
            evidence={
                "attempts in 7 days": int(rec),
                "reference rate": round(float(base_rate), 1),
                "opened": 0,
            },
        ))
    return out


def _screen_jump(df: pd.DataFrame) -> list[Signal]:
    """The obvious rule: "screen time has gone up a lot".

    It is here so we can show it **does not fire** on this data. It is the
    system's negative control.
    """
    out: list[Signal] = []
    need = DRIFT_RECENT + DRIFT_BASE
    for i in range(need - 1, len(df)):
        rec = df.screen_min.iloc[i - DRIFT_RECENT + 1: i + 1].median()
        base = max(df.screen_min.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE:
                                      i - DRIFT_RECENT + 1].median(), 1.0)
        if rec >= SCREEN_JUMP_RATIO * base and rec - base >= SCREEN_JUMP_ABS:
            out.append(Signal(
                key="screen_jump", day=df.day.iloc[i],
                headline="Screen time has gone up",
                guardian_text="Daily use has grown against previous weeks.",
                magnitude=_clamp((rec / base - 1) * 2),
                persistence=1.0, actionability=0.5,
                evidence={"recent median (min)": round(float(rec)),
                          "reference (min)": round(float(base))}))
    return out


RULES = (_night_drift, _sensitive_spike, _screen_jump)


# ---------------------------------------------------------------------------
# Silence budget
# ---------------------------------------------------------------------------

def _decide(signals: list[Signal]) -> list[Signal]:
    """Allocates the alert quota and records why each leftover is dropped.

    First, repeats are collapsed: a rule that holds for 9 days running is
    **one** fact, not nine alerts. Then candidates are sorted by priority and
    the quota is handed out respecting a minimum gap.
    """
    # 1 · collapse runs of the same rule into a single episode
    episodes: list[Signal] = []
    for s in sorted(signals, key=lambda x: (x.key, x.day)):
        prev = next((e for e in episodes if e.key == s.key), None)
        same_run = prev and (s.day - (prev.until or prev.day)).days <= 14
        if same_run:
            # The evidence stays that of the firing day, not the last one:
            # it is what justifies the alert sent that day.
            prev.magnitude = max(prev.magnitude, s.magnitude)
            prev.persistence = max(prev.persistence, s.persistence)
            prev.until = s.day
            continue
        episodes.append(s)

    # 2 · hand out the quota
    sent: list[Signal] = []
    for s in sorted(episodes, key=lambda x: -x.priority):
        if s.actionability < 0.5:
            s.decision, s.reason = "summary", (
                "The phone already resolved the incident; there is nothing a "
                "guardian can do today that they cannot do on Sunday. It goes "
                "to the weekly summary, not to a notification.")
            continue
        if len(sent) >= ALERT_BUDGET:
            s.decision, s.reason = "discarded", (
                f"Quota spent: {ALERT_BUDGET} alerts per month. A higher "
                f"priority signal was already through and this one does not "
                f"beat it.")
            continue
        if any(abs((s.day - o.day).days) < ALERT_MIN_GAP_DAYS for o in sent):
            s.decision, s.reason = "summary", (
                f"There is another alert less than {ALERT_MIN_GAP_DAYS} days "
                f"away. Two notifications back to back read as noise, not as "
                f"urgency.")
            continue
        s.decision, s.reason = "sent", "Sustained and actionable change."
        sent.append(s)

    return sorted(episodes, key=lambda x: (x.decision != "sent", -x.priority))


def evaluate_alerts(df: pd.DataFrame) -> list[Signal]:
    """Every candidate in the period, with its verdict."""
    signals: list[Signal] = []
    for rule in RULES:
        signals.extend(rule(df))
    return _decide(signals)


def guardian_digest(df: pd.DataFrame, signals: list[Signal]) -> dict:
    """The only thing leaving the device when there is no alert: a coarse digest.

    No apps, no domains, no categories, and the numbers rounded. The rounding is
    not cosmetic: at this granularity the guardian makes exactly the same
    decisions, and in exchange the aggregate stops being an identifier.
    """
    last7 = df.tail(7)
    state = ("something has changed" if any(s.decision == "sent" for s in signals)
             else "all in order")
    # Streak of protected nights. Streaks are an object-free aggregate: they
    # say something is going well without saying what against.
    streak = 0
    for night in reversed(list(df["night_min"])):
        if night >= POS_NIGHT_QUIET_MIN:
            break
        streak += 1
    return {
        "status": state,
        "screen time per day": f"about {round(last7.screen_min.mean() / 15) * 15 / 60:.1f} h",
        "wellbeing index": f"{round(last7.score.mean() / 5) * 5:.0f} out of 100",
        "nights in a row without late use": str(streak),
        "the filter acted": ("more than usual"
                             if last7.blocks.mean() > df.blocks.mean() * 1.2
                             else "as usual"),
        "sensitive content opened": "none",
    }


# ---------------------------------------------------------------------------
# Nudge · user-facing, on device
# ---------------------------------------------------------------------------

NUDGE_COPY = (
    "That is the {n}th time you have opened your phone tonight.\n"
    "A month ago you had already put it down by now."
)


def replay_nudge(tl: Timeline, df: pd.DataFrame) -> list[NightNudge]:
    """Replays the nudge over history: when it would have shown and what was at
    stake when it did.

    You cannot A/B test a closed file, but you can measure the nudge's
    **ceiling**: the night screen minutes that happen *after* the moment it
    would have appeared. That bounds what it can recover, and the number of
    nights without a trigger bounds how much it annoys.
    """
    out: list[NightNudge] = []
    baseline = df.set_index("day")["night_min_baseline"].to_dict()
    recent3 = df.set_index("day")["night_min"].rolling(3, min_periods=1).median().to_dict()

    for d in df.day:
        n0, n1 = _night_window(d)
        ivs = sorted([i for i in tl.intervals if i.end_ms > n0 and i.start_ms < n1],
                     key=lambda i: i.start_ms)
        night_min = sum((min(i.end_ms, n1) - max(i.start_ms, n0)) / 60_000 for i in ivs)
        arm_from = n0 + NUDGE_AFTER_MIN * 60_000
        reopens = [i for i in ivs if i.is_pickup and i.start_ms >= arm_from]

        quiet = ""
        if len(reopens) < NUDGE_MIN_REOPENS:
            quiet = ("A single reopening: staying up late one night is not a "
                     "pattern, and alerting on it teaches people to ignore the "
                     "alert.")
        else:
            base, rec = baseline.get(d), recent3.get(d)
            if base is not None and rec is not None and not pd.isna(base) and rec < base:
                quiet = ("The last few nights are already better than their own "
                         "median; when someone is correcting on their own, the "
                         "useful thing is to stay quiet.")

        fired = not quiet and len(reopens) >= NUDGE_MIN_REOPENS
        at = reopens[NUDGE_MIN_REOPENS - 1].start_ms if fired else None
        after = (sum((min(i.end_ms, n1) - max(i.start_ms, at)) / 60_000
                     for i in ivs if i.end_ms > at) if fired else 0.0)

        out.append(NightNudge(d, fired, at, quiet, len(reopens), after, night_min))
    return out


def nudge_summary(nudges: list[NightNudge]) -> dict:
    fired = [n for n in nudges if n.fired]
    night_total = sum(n.night_minutes for n in nudges)
    after = sum(n.minutes_after for n in fired)
    return {
        "nights": len(nudges),
        "nights with a nudge": len(fired),
        "appearance rate": len(fired) / max(len(nudges), 1),
        "total night minutes": night_total,
        "minutes at stake after the nudge": after,
        "share of night total": after / night_total if night_total else 0.0,
        "minutes at stake per nudged night": after / len(fired) if fired else 0.0,
        "median nudge time": (
            sorted(to_dt(n.at_ms).hour + to_dt(n.at_ms).minute / 60 % 24
                   for n in fired)[len(fired) // 2] if fired else None),
    }


# ---------------------------------------------------------------------------
# Month walkthrough · what the phone knew and emitted each day
# ---------------------------------------------------------------------------

def month_replay(df: pd.DataFrame, nudges: list[NightNudge],
                 positives: list[Signal] | None = None) -> list[dict]:
    """The system state at the close of each day, using the information it had
    that day and not the whole month's.

    **Alerts** are re-evaluated over the history available up to each date:
    their quota allocation sorts by priority, so it depends on the set and has
    to be recomputed to know what would have been sent that day.

    **Reinforcements** are not: each rule only looks backwards and the quota is
    a forward pass with memory, so `evaluate_positives` over the full frame
    already gives the causal result. Recomputing them per prefix would reset
    the quota every day and multiply the sends.
    """
    positives = positives or []
    pos_by_day: dict[date, list[Signal]] = {}
    for s in positives:
        if s.decision == "sent":
            pos_by_day.setdefault(s.day, []).append(s)
    by_day = {n.day: n for n in nudges}
    out: list[dict] = []

    for i, day in enumerate(df["day"]):
        upto = df.iloc[: i + 1]
        sigs = evaluate_alerts(upto)
        pos_today = pos_by_day.get(day, [])
        sent_today = next((s for s in sigs
                           if s.decision == "sent" and s.day == day), None)
        digest_today = next((s for s in sigs
                             if s.decision == "summary" and s.day == day), None)
        nudge = by_day.get(day)

        out.append({
            "day": day,
            "alert": sent_today,
            "digest_entry": digest_today,
            "nudge": nudge,
            "positives": pos_today,
            "positives_so_far": sum(
                len(v) for k, v in pos_by_day.items() if k <= day),
            # running totals at that date, as the guardian would see them
            "alerts_so_far": sum(1 for s in sigs if s.decision == "sent"),
            "digest_so_far": sum(1 for s in sigs if s.decision == "summary"),
            "nudges_so_far": sum(1 for n in nudges if n.fired and n.day <= day),
            "status": ("something has changed"
                       if any(s.decision == "sent" for s in sigs)
                       else "all in order"),
        })
    return out


def emissions(replay: list[dict]) -> list[dict]:
    """A flat list of everything the phone emitted, in time order.

    Three possible destinations and only three: the user's screen (nudge), a
    guardian notification (alert) and the weekly summary (held signal).
    """
    out: list[dict] = []
    for r in replay:
        if r["nudge"] and r["nudge"].fired:
            out.append({
                "day": r["day"], "destination": "User · screen",
                "type": "Night nudge",
                "detail": (f"reopening no. {r['nudge'].reopens} of the night · "
                           f"{r['nudge'].minutes_after:.0f} min of screen after"),
            })
        if r["alert"]:
            out.append({
                "day": r["day"], "destination": "Guardian · notification",
                "type": r["alert"].key, "detail": r["alert"].headline,
            })
        if r["digest_entry"]:
            out.append({
                "day": r["day"], "destination": "Guardian · weekly summary",
                "type": r["digest_entry"].key,
                "detail": r["digest_entry"].headline,
            })
        for s in r.get("positives", []):
            out.append({
                "day": r["day"],
                "destination": ("User · reinforcement" if s.audience == "user"
                                else "Guardian · reinforcement"),
                "type": s.key, "detail": s.headline,
            })
    return sorted(out, key=lambda x: x["day"])


# ---------------------------------------------------------------------------
# Positive reinforcement
# ---------------------------------------------------------------------------
#
# Design criteria, in three rules:
#
# 1. **Against yourself, not against a table.** An absolute threshold always
#    congratulates user A and never user B, which is the opposite of useful.
#    Every reinforcement compares the person with their own recent weeks.
#
# 2. **Only changes with margin.** A minimum margin over the best recent record
#    is required (10 % for records, 30 % for weekly aggregates) so daily noise
#    triggers nothing. A record beaten by one minute is not a record, it is
#    variance.
#
# 3. **Descriptive, never prescriptive.** The text says what happened and what
#    it is compared against. It does not congratulate in the second person nor
#    suggest what to do next; that turns a measurement into an opinion.
#
# Budget: at most one reinforcement per week and audience. The rest accumulates
# in the weekly summary, which is where the full picture lives.

#: Minimum margin before a record counts as genuinely beaten.
POS_RECORD_MARGIN = 1.10
#: Absolute floor for the disconnection record: 90 min without looking at the
#: phone is nobody's achievement.
POS_OFFLINE_FLOOR_H = 3.0
#: Milestones for the protected-night streak.
POS_STREAK_MILESTONES = (7, 14, 30)
#: A night counts as protected below this threshold.
POS_NIGHT_QUIET_MIN = 5.0
#: Weeks shorter than this generate no reinforcement: a three-day week always
#: looks better than a seven-day one.
POS_MIN_WEEK_DAYS = 5
#: Reinforcement quota per audience.
POS_BUDGET_DAYS = 7


def _num(x: float, dec: int = 1) -> str:
    """One decimal place, kept in a helper so the copy stays consistent."""
    return f"{x:.{dec}f}"


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _weeks(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly aggregate, only the weeks that are long enough."""
    w = df.groupby("week").agg(
        days=("day", "count"), last_day=("day", "max"),
        screen=("screen_min", "mean"), pickups=("pickups", "mean"),
        night=("night_min", "mean"), blocks=("blocks", "mean"),
        sensitive=("blocks_sensitive", "sum"),
        distract=("distract_share", "mean"), score=("score", "mean"),
    )
    return w[w.days >= POS_MIN_WEEK_DAYS]


def _pos(key, day, headline, text, evidence, audience="user") -> Signal:
    return Signal(key=key, day=day, headline=headline, guardian_text=text,
                  magnitude=1.0, persistence=1.0, actionability=1.0,
                  evidence=evidence, audience=audience, tone="reinforcement")


def _offline_record(df: pd.DataFrame) -> list[Signal]:
    """Best screen-free stretch of the last two weeks."""
    out = []
    off = (df["longest_offline_s"] / 3600).reset_index(drop=True)
    days = df["day"].reset_index(drop=True)
    for i in range(14, len(df)):
        prev = off.iloc[i - 14:i].max()
        v = off.iloc[i]
        if v >= max(prev * POS_RECORD_MARGIN, POS_OFFLINE_FLOOR_H):
            out.append(_pos(
                "offline_record", days.iloc[i],
                "Longest screen-free stretch of the last two weeks",
                f"{_hm(v * 60)} in a row without turning the screen on. The best "
                f"record of the previous two weeks was {_hm(prev * 60)}.",
                {"stretch (h)": round(float(v), 2),
                 "best of 14 days (h)": round(float(prev), 2)}))
    return out


def _night_streak(df: pd.DataFrame) -> list[Signal]:
    """Consecutive nights with no screen inside the protected band."""
    out, streak = [], 0
    for day, night in zip(df["day"], df["night_min"]):
        streak = streak + 1 if night < POS_NIGHT_QUIET_MIN else 0
        if streak in POS_STREAK_MILESTONES:
            out.append(_pos(
                "night_streak", day,
                f"{streak} nights in a row with no late-night screen",
                f"{streak} consecutive nights without turning the screen on "
                f"between 23:00 and 06:00.",
                {"consecutive nights": streak}))
    return out


def _calm_week(df: pd.DataFrame) -> list[Signal]:
    """A week with fewer filter interventions than the previous two."""
    out, w = [], _weeks(df)
    for i in range(2, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 2:i]
        base = prev.blocks.mean()
        if base >= 1 and cur.blocks <= base * 0.7:
            out.append(_pos(
                "calm_week", cur.last_day,
                "The filter stepped in less than in previous weeks",
                f"This week the filter acted {_num(cur.blocks)} times a day, "
                f"against {_num(base)} over the previous two weeks.",
                {"blocks/day this week": round(float(cur.blocks), 2),
                 "blocks/day previous 2 weeks": round(float(base), 2)}))
    return out


def _focus_week(df: pd.DataFrame) -> list[Signal]:
    """A week with a smaller share of time in social, entertainment and games."""
    out, w = [], _weeks(df)
    for i in range(1, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 1]
        if prev.distract >= 0.10 and cur.distract <= prev.distract * 0.8:
            out.append(_pos(
                "focus_week", cur.last_day,
                "Less time in social, entertainment and games than last week",
                f"This week {cur.distract*100:.0f} % of screen time went to "
                f"social, entertainment or games, against "
                f"{prev.distract*100:.0f} % the week before.",
                {"share this week": f"{cur.distract*100:.1f} %",
                 "share last week": f"{prev.distract*100:.1f} %"}))
    return out


def _best_week(df: pd.DataFrame) -> list[Signal]:
    """Highest weekly index in the available history."""
    out, w = [], _weeks(df)
    for i in range(3, len(w)):
        cur, prev = w.iloc[i], w.iloc[:i]
        if cur.score > prev.score.max():
            out.append(_pos(
                "best_week", cur.last_day,
                "Highest weekly index of the period",
                f"This week's index is {cur.score:.0f} out of 100, the highest "
                f"since records began. The previous best was "
                f"{prev.score.max():.0f}.",
                {"index this week": round(float(cur.score), 1),
                 "previous best": round(float(prev.score.max()), 1)}))
    return out


def _filter_calm(df: pd.DataFrame) -> list[Signal]:
    """A clear drop in attempts towards sensitive content. Goes to the guardian.

    It is the exact reverse of `sensitive_spike`, at the same granularity: no
    figures, no objects, no categories. A guardian who only hears from the
    product when something gets worse ends up reading the channel as a threat.
    """
    out, w = [], _weeks(df)
    for i in range(1, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 1]
        if prev.sensitive >= 10 and cur.sensitive <= prev.sensitive * 0.6:
            out.append(_pos(
                "filter_calm", cur.last_day,
                "The sensitive-content filter stepped in less",
                "This week the sensitive-content filter stepped in considerably "
                "less than last week. No content opened, as in previous weeks.",
                {"attempts this week": int(cur.sensitive),
                 "attempts last week": int(prev.sensitive)},
                audience="guardian"))
    return out


POSITIVE_RULES = (_offline_record, _night_streak, _calm_week,
                  _focus_week, _best_week, _filter_calm)


def evaluate_positives(df: pd.DataFrame, has_guardian: bool = True) -> list[Signal]:
    """Candidate reinforcements, with a quota of one per week and audience.

    Whatever does not fit the quota is not discarded: it drops to the weekly
    summary, where the user sees the full picture without being interrupted.
    """
    signals: list[Signal] = []
    for rule in POSITIVE_RULES:
        signals.extend(rule(df))
    if not has_guardian:
        signals = [s for s in signals if s.audience != "guardian"]

    last_sent: dict[str, date] = {}
    for s in sorted(signals, key=lambda x: x.day):
        prev = last_sent.get(s.audience)
        if prev and (s.day - prev).days < POS_BUDGET_DAYS:
            s.decision = "summary"
            s.reason = (f"A reinforcement went to this audience less than "
                        f"{POS_BUDGET_DAYS} days ago. It enters the weekly "
                        f"summary instead.")
            continue
        s.decision, s.reason = "sent", "Measurable improvement over own history."
        last_sent[s.audience] = s.day
    return sorted(signals, key=lambda x: x.day)
