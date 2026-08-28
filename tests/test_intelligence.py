"""
Layer 3: what gets surfaced, to whom, and what stays quiet.

Three groups of test:

* **Behaviour over the real data.** The claims the dashboard makes on screen
  ("night_drift fires on 19 May", "screen_jump fires on neither profile")
  become assertions here. If a recalibration breaks them, the test says so
  before the reader does.
* **Allocation properties.** Quotas, minimum gaps, cadence.
* **The privacy contract.** What goes out to a guardian cannot contain app
  names, domains or categories.
"""

from __future__ import annotations

import datetime as dt
import json

from balance.events import CATEGORIES
from balance.intelligence import (
    ALERT_BUDGET, ALERT_MIN_GAP_DAYS, POS_BUDGET_DAYS, emissions,
    evaluate_alerts, evaluate_positives, guardian_digest, month_replay,
    nudge_summary, replay_nudge,
)


# ---------------------------------------------------------------------------
# Guardian alerts
# ---------------------------------------------------------------------------

def test_night_drift_fires_on_19_may_for_b_only(df_a, df_b):
    a = [s for s in evaluate_alerts(df_a) if s.key == "night_drift"]
    b = [s for s in evaluate_alerts(df_b) if s.key == "night_drift"]
    assert a == [], "user A has no night drift to detect"
    assert len(b) == 1
    assert b[0].day == dt.date(2026, 5, 19)
    assert b[0].decision == "sent"


def test_screen_jump_fires_on_neither_profile(df_a, df_b):
    """Negative control: the conventional volume rule.

    It is the one almost any implementation would reach for first, and on this
    data it detects nothing: B's daily use rises 8 % while their night band
    multiplies by 13.
    """
    for df in (df_a, df_b):
        assert [s for s in evaluate_alerts(df) if s.key == "screen_jump"] == []


def test_the_sensitive_content_spike_is_not_notified(df_b):
    """Detected and dropped to the weekly summary: the filter already stopped
    it, and the conversation left gains nothing by arriving today."""
    spike = [s for s in evaluate_alerts(df_b) if s.key == "sensitive_spike"]
    assert len(spike) == 1
    assert spike[0].decision == "summary"
    assert spike[0].actionability < 0.5


def test_the_alert_quota_is_respected(df_a, df_b):
    for df in (df_a, df_b):
        sent = [s for s in evaluate_alerts(df) if s.decision == "sent"]
        assert len(sent) <= ALERT_BUDGET
        dates = sorted(s.day for s in sent)
        for x, y in zip(dates, dates[1:]):
            assert (y - x).days >= ALERT_MIN_GAP_DAYS


def test_every_dropped_signal_carries_a_reason(df_b):
    for s in evaluate_alerts(df_b):
        if s.decision != "sent":
            assert s.reason, f"{s.key} is dropped without explaining why"


def test_a_run_of_days_is_one_episode_not_one_per_day(df_b):
    """The rule holds from 19 to 23 May. That is one fact, not five."""
    drift = [s for s in evaluate_alerts(df_b) if s.key == "night_drift"][0]
    assert drift.days_true == 5
    assert drift.until == dt.date(2026, 5, 23)


# ---------------------------------------------------------------------------
# Reinforcements
# ---------------------------------------------------------------------------

def test_the_healthy_profile_receives_reinforcements(df_a):
    """A system that only speaks when something gets worse reads as a threat."""
    pos = [s for s in evaluate_positives(df_a, has_guardian=False)
           if s.decision == "sent"]
    assert len(pos) >= 2
    assert all(s.audience == "user" for s in pos)


def test_no_guardian_means_no_guardian_reinforcements(df_a):
    pos = evaluate_positives(df_a, has_guardian=False)
    assert all(s.audience != "guardian" for s in pos)


def test_b_guardian_receives_an_alert_and_a_reinforcement(df_b):
    """The guardian channel cannot be only bad news."""
    alerts = [s for s in evaluate_alerts(df_b) if s.decision == "sent"]
    positives = [s for s in evaluate_positives(df_b, True)
                 if s.decision == "sent" and s.audience == "guardian"]
    assert len(alerts) == 1 and len(positives) == 1


def test_the_reinforcement_quota_keeps_at_least_a_week_apart(df_a, df_b):
    for df, hg in ((df_a, False), (df_b, True)):
        sent = [s for s in evaluate_positives(df, hg) if s.decision == "sent"]
        by_audience = {}
        for s in sorted(sent, key=lambda x: x.day):
            prev = by_audience.get(s.audience)
            if prev:
                assert (s.day - prev).days >= POS_BUDGET_DAYS
            by_audience[s.audience] = s.day


def test_reinforcements_do_not_give_instructions(df_a, df_b):
    """The tone is descriptive. If a recommendation slips in, this catches it."""
    banned = ("you should", "try to", "we recommend", "good time to",
              "you could", "remember to", "make sure you", "consider ")
    for df, hg in ((df_a, False), (df_b, True)):
        for s in evaluate_positives(df, hg) + evaluate_alerts(df):
            text = s.guardian_text.lower()
            for phrase in banned:
                assert phrase not in text, f"{s.key}: \"{s.guardian_text}\""


# ---------------------------------------------------------------------------
# On-device nudge
# ---------------------------------------------------------------------------

def test_the_nudge_does_not_fire_on_the_healthy_profile(tl_a, df_a):
    ns = nudge_summary(replay_nudge(tl_a, df_a))
    assert ns["nights with a nudge"] == 0, "zero false positives, no config needed"


def test_the_nudge_fires_on_b_and_leaves_measurable_headroom(tl_b, df_b):
    ns = nudge_summary(replay_nudge(tl_b, df_b))
    assert ns["nights with a nudge"] == 14
    assert 0.30 < ns["share of night total"] < 0.45


def test_every_night_without_a_nudge_has_a_reason(tl_b, df_b):
    for n in replay_nudge(tl_b, df_b):
        assert n.fired or n.quiet_reason, f"{n.day}: neither fires nor explains"


# ---------------------------------------------------------------------------
# Privacy contract
# ---------------------------------------------------------------------------

def _guardian_text(tl, df, has_guardian: bool) -> str:
    """Everything that would leave the device towards a guardian, concatenated."""
    sigs = evaluate_alerts(df) + evaluate_positives(df, has_guardian)
    pieces = [s.guardian_text for s in sigs
              if s.audience == "guardian" and s.decision == "sent"]
    pieces += [s.headline for s in sigs
               if s.audience == "guardian" and s.decision == "sent"]
    pieces.append(json.dumps(guardian_digest(df, sigs), ensure_ascii=False))
    return " ".join(pieces).lower()


def test_the_guardian_payload_contains_no_apps_or_domains(tl_b, df_b):
    """The privacy contract, as an assertion rather than a README promise."""
    outbound = _guardian_text(tl_b, df_b, True)

    packages = {e["package_name"] for e in tl_b.events if e["package_name"]}
    domains = {e["url_domain"] for e in tl_b.events if e["url_domain"]}

    # The full identifier is checked and so is its stem ("pornhub" from
    # pornhub.com, "whatsapp" from com.whatsapp), which is how a value would
    # actually leak. Stems under four letters are skipped: the "x" of x.com
    # appears in any prose and would be a false positive.
    def stems(ident: str) -> list[str]:
        parts = [ident] + ident.replace("/", ".").split(".")
        return [p.lower() for p in parts if len(p) >= 4]

    for ident in packages | domains:
        for stem in stems(ident):
            assert stem not in outbound, f"\"{stem}\" leaked to the guardian"


def test_the_guardian_payload_names_no_categories(tl_b, df_b):
    outbound = _guardian_text(tl_b, df_b, True)
    for cat in CATEGORIES:
        assert cat.lower() not in outbound


def test_the_guardian_digest_is_rounded(df_b):
    """A fine-grained value ("247 minutes, index 41.3") identifies a person."""
    d = guardian_digest(df_b, evaluate_alerts(df_b))
    assert d["screen time per day"].startswith("about ")
    index = int(d["wellbeing index"].split()[0])
    assert index % 5 == 0, "the index comes out in multiples of 5"
    assert d["sensitive content opened"] == "none"


def test_no_sensitive_content_ever_opened(tl_a, tl_b):
    """The claim the guardian digest transmits, verified against the stream:
    there is no URL_VISIT nor APP_FOREGROUND with those categories."""
    from balance.events import SENSITIVE
    for tl in (tl_a, tl_b):
        opened = [e for e in tl.events
                  if e["event_type"] in ("URL_VISIT", "APP_FOREGROUND")
                  and e["category"] in SENSITIVE]
        assert opened == []


# ---------------------------------------------------------------------------
# Month walkthrough
# ---------------------------------------------------------------------------

def test_the_walkthrough_does_not_reset_the_reinforcement_quota(tl_b, df_b):
    """A real bug: recomputing reinforcements per prefix reset the quota every
    day and multiplied the sends. They must match the single computation."""
    pos = evaluate_positives(df_b, True)
    replay = month_replay(df_b, replay_nudge(tl_b, df_b), pos)
    in_walkthrough = sum(len(r["positives"]) for r in replay)
    expected = sum(1 for s in pos if s.decision == "sent")
    assert in_walkthrough == expected


def test_the_walkthrough_only_uses_past_information(tl_b, df_b):
    """The phone on the 12th did not know what would happen on the 19th."""
    replay = month_replay(df_b, replay_nudge(tl_b, df_b),
                          evaluate_positives(df_b, True))
    for r in replay:
        if r["alert"]:
            assert r["alert"].day == r["day"]
        assert r["alerts_so_far"] <= ALERT_BUDGET


def test_emissions_cover_the_three_destinations(tl_b, df_b):
    replay = month_replay(df_b, replay_nudge(tl_b, df_b),
                          evaluate_positives(df_b, True))
    destinations = {e["destination"] for e in emissions(replay)}
    assert "User · screen" in destinations
    assert "Guardian · notification" in destinations
    assert "Guardian · reinforcement" in destinations


def test_the_decision_vocabulary_is_the_one_the_charts_expect():
    """The rail markers key off these exact strings.

    They were left in Spanish once during the translation and the guardian
    markers silently vanished from the walkthrough: the traces were built from
    an empty list and nothing failed.
    """
    from balance.intelligence import Signal
    import balance.charts as charts
    import inspect

    source = inspect.getsource(charts.tracked_series)
    assert '== "sent"' in source
    assert '== "summary"' in source
    assert Signal(key="k", day=dt.date(2026, 5, 1), headline="h",
                  guardian_text="t", magnitude=1, persistence=1,
                  actionability=1).decision == "candidate"
