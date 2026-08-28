"""
The event file as the system of record.

Here the data is the subject of the test, not the code. Two things:

* **Input contract.** Eight fields, time order, closed enums. If a new file
  breaks it, this says so before the error surfaces as an odd number in a
  chart.
* **Published claims.** Every figure the dashboard or the notes put on screen
  is recomputed here by a different path. A claim without a test is a claim
  that expires at the next recalibration.
"""

from __future__ import annotations

import json

import pytest

from balance.events import BLOCK, CATEGORIES, SENSITIVE, load
from conftest import DATA

FIELDS = {"id", "event_type", "timestamp_millis", "package_name",
          "url_domain", "category", "block_type", "is_keyguard_locked"}
TYPES = {"SCREEN_ON", "SCREEN_OFF", "USER_PRESENT", "APP_FOREGROUND",
         "URL_VISIT", "BLOCK"}
FILES = ["events_user_a.json", "events_user_b.json"]


@pytest.fixture(scope="module", params=FILES)
def raw(request):
    return json.loads((DATA / request.param).read_text())


# ---------------------------------------------------------------------------
# Input contract
# ---------------------------------------------------------------------------

def test_every_event_has_the_eight_fields(raw):
    for e in raw:
        assert set(e) == FIELDS


def test_the_event_types_are_the_documented_ones(raw):
    assert {e["event_type"] for e in raw} <= TYPES


def test_the_categories_come_from_the_enum(raw):
    vistas = {e["category"] for e in raw if e["category"]}
    assert vistas <= set(CATEGORIES)


def test_ids_are_monotonic_and_time_is_ordered(raw):
    ids = [e["id"] for e in raw]
    ts = [e["timestamp_millis"] for e in raw]
    assert ids == sorted(ids)
    assert ts == sorted(ts)


def test_fields_apply_to_their_event_type(raw):
    for e in raw:
        t = e["event_type"]
        if t == "APP_FOREGROUND":
            assert e["package_name"] and e["category"]
            assert e["url_domain"] is None
        elif t == "URL_VISIT":
            assert e["url_domain"] and e["category"]
            assert e["package_name"] is None
        elif t == BLOCK:
            assert e["block_type"] in {"APP", "URL", "NUDITY"}
            assert e["package_name"] or e["url_domain"]
        elif t == "USER_PRESENT":
            assert e["is_keyguard_locked"] is False
        elif t == "SCREEN_OFF":
            assert e["is_keyguard_locked"] is None


def test_domains_carry_no_path_or_query(raw):
    """The format promises domain only. A path arriving here would be personal
    data that should not be in the stream."""
    for e in raw:
        d = e["url_domain"]
        if d:
            assert "/" not in d and "?" not in d and " " not in d


# ---------------------------------------------------------------------------
# Published claims
# ---------------------------------------------------------------------------

def test_screen_overlap_exists_in_the_declared_amount():
    """"77 SCREEN_ON in A and 411 in B while the screen was already on".

    Counted with the same depth model `events.py` uses. A boolean model
    (on/off, no nesting) gives 74 and 345: it collapses depth-3 overlaps, and
    those were the figures published by mistake before this test existed.
    """
    expected = {"events_user_a.json": 77, "events_user_b.json": 411}
    for filename, n in expected.items():
        events = json.loads((DATA / filename).read_text())
        depth = overlaps = 0
        for e in events:
            if e["event_type"] == "SCREEN_ON":
                if depth > 0:
                    overlaps += 1
                depth += 1
            elif e["event_type"] == "SCREEN_OFF":
                depth = max(0, depth - 1)
        assert overlaps == n, f"{filename}: {overlaps} overlaps, {n} declared"


def test_the_pairing_chosen_changes_the_result_both_ways():
    """Justifies the depth counter with numbers rather than intuition.

    LIFO counts the overlap twice and FIFO loses the trailing stretch. The
    union sits in between and, unlike the other two, does not depend on which
    OFF is paired with which ON.
    """
    tl = load(DATA / "events_user_a.json", "A")
    union_h = sum(i.seconds for i in tl.intervals) / 3600

    fifo_s, open_at = 0.0, None
    lifo_s, stack = 0.0, []
    for e in tl.events:
        t, ts_ = e["event_type"], e["timestamp_millis"]
        if t == "SCREEN_ON":
            if open_at is None:
                open_at = ts_
            stack.append(ts_)
        elif t == "SCREEN_OFF":
            if open_at is not None:
                fifo_s += (ts_ - open_at) / 1000
                open_at = None
            if stack:
                lifo_s += (ts_ - stack.pop()) / 1000

    assert round(union_h, 1) == 61.1
    assert round(fifo_s / 3600, 1) == 56.7, "FIFO comes up short"
    assert round(lifo_s / 3600, 1) == 64.9, "LIFO overshoots"
    assert fifo_s / 3600 < union_h < lifo_s / 3600


def test_a_never_turns_the_screen_on_at_night(df_a):
    """The dashboard's most repeated claim."""
    assert df_a["night_min"].sum() == 0
    assert df_a["night_pickups"].sum() == 0


def test_a_records_no_sensitive_content(df_a):
    assert df_a["blocks_sensitive"].sum() == 0


def test_b_volume_barely_moves_while_the_night_multiplies(df_b):
    """"+8 % of screen time, ×13 of late-night between week 1 and week 4"."""
    s1 = df_b[df_b.week == 1]["screen_min"].mean()
    s4 = df_b[df_b.week == 4]["screen_min"].mean()
    n1 = df_b[df_b.week == 1]["night_min"].mean()
    n4 = df_b[df_b.week == 4]["night_min"].mean()

    assert 1.05 < s4 / s1 < 1.12, "volume rises little"
    assert n4 / n1 > 10, "the night band multiplies by more than ten"


def test_b_sleep_window_shrinks_by_about_95_minutes(df_b):
    def w(col, k):
        return df_b[df_b.week == k][col].median()
    v1 = (24 + w("first_pickup_h", 1)) - w("night_end_h", 1)
    v4 = (24 + w("first_pickup_h", 4)) - w("night_end_h", 4)
    assert -140 < (v4 - v1) * 60 < -50


def test_a_blocks_fall_across_the_month(df_a):
    """"from 19 in week 1 to 3 in week 4"."""
    assert df_a[df_a.week == 1]["blocks"].sum() == 19
    assert df_a[df_a.week == 4]["blocks"].sum() == 3


def test_b_sensitive_attempts_are_a_spike_not_a_trend(df_b):
    """"145 of 203 (71 %) in weeks 2 and 3, and 30 in week 4"."""
    per_week = df_b.groupby("week")["blocks_sensitive"].sum()
    assert per_week.sum() == 203
    assert per_week.loc[[2, 3]].sum() == 145
    assert per_week.loc[4] == 30


def test_sensitive_attempt_persistence_is_low(tl_b):
    """"bursts of 1.2 attempts on average, 3 at most" grouped at 10 minutes."""
    sens = sorted((b for b in tl_b.blocks if b.category in SENSITIVE),
                  key=lambda b: b.ts_ms)
    bursts, current = [], [sens[0]]
    for b in sens[1:]:
        if b.ts_ms - current[-1].ts_ms <= 10 * 60_000:
            current.append(b)
        else:
            bursts.append(current)
            current = [b]
    bursts.append(current)
    sizes = [len(r) for r in bursts]

    assert max(sizes) == 3
    assert 1.1 <= sum(sizes) / len(sizes) <= 1.3


def test_the_distraction_share_is_similar_on_both(df_a, df_b):
    """The counterintuitive one: B's problem is not the category split."""
    a = df_a["distract_share"].mean()
    b = df_b["distract_share"].mean()
    assert abs(a - b) < 0.05


def test_the_block_totals_add_up(df_a, df_b):
    """Invariant: the per-type sum is the total, with no overlap and no gap."""
    for df in (df_a, df_b):
        per_type = df["blocks_app"] + df["blocks_url"] + df["blocks_nudity"]
        assert (per_type == df["blocks"]).all()


def test_attribution_coverage_matches_the_claim(tl_a, tl_b, df_a, df_b):
    """"86 % in A and 67 % in B"."""
    for tl, df, expected in ((tl_a, df_a, 86), (tl_b, df_b, 67)):
        days = set(df["day"])
        screen = sum(i.seconds for i in tl.intervals if i.day in days)
        attributed = sum(u.seconds for u in tl.usages if u.day in days)
        assert round(attributed / screen * 100) == expected
