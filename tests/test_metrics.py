"""
Layer 1: the definitions behind the daily metrics.

Each test pins a decision made in `metrics.py` that is not obvious from the
input format alone: where the night cuts, where the day starts, what happens to
a truncated day.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from balance.metrics import WAKE_END, WAKE_START, daily_frame, weekly_frame
from conftest import DAY0, build, ev


def _frame(events, tmp_path):
    return daily_frame(build(events, tmp_path=tmp_path))


def _full_day(day_offset: int) -> list[dict]:
    """Filler activity that pushes a day past the coverage threshold.

    `daily_frame` drops days the file only partly covers; without this filler,
    any short synthetic stream would fall out of the frame entirely.
    """
    return [
        ev("SCREEN_ON", day_offset, "07:00", is_keyguard_locked=True),
        ev("USER_PRESENT", day_offset, "07:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", day_offset, "07:05"),
        ev("SCREEN_ON", day_offset, "21:00", is_keyguard_locked=True),
        ev("USER_PRESENT", day_offset, "21:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", day_offset, "21:05"),
    ]


def test_the_night_runs_from_23_to_6_the_next_day(tmp_path):
    """The calendar day cuts at midnight, the night does not: otherwise one
    night shows up split across two rows and the signal is diluted."""
    df = _frame(
        _full_day(0) + [
            ev("SCREEN_ON", 0, "23:30", is_keyguard_locked=True),
            ev("USER_PRESENT", 0, "23:30:02", is_keyguard_locked=False),
            ev("SCREEN_OFF", 1, "00:30"),
        ] + _full_day(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_min"] == 60, "the 60 minutes belong to day 0's night"
    assert df.loc[DAY0 + dt.timedelta(days=1), "night_min"] == 0
    # and daily screen time is still split at midnight
    assert round(df.loc[DAY0, "screen_min"]) == 10 + 30
    assert round(df.loc[DAY0 + dt.timedelta(days=1), "screen_min"]) == 30 + 10


def test_the_first_pickup_has_a_floor_at_06(tmp_path):
    """A day starting at 00:20 has not begun: the previous one has not ended.
    That phenomenon is measured in `night_*`, not in `first_pickup_h`."""
    df = _frame([
        ev("SCREEN_ON", 0, "00:20", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "00:20:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "00:50"),
    ] + _full_day(0), tmp_path=tmp_path)

    assert df.loc[DAY0, "first_pickup_h"] == 7.0, \
        "the 00:20 unlock does not count as the start of the day"


def test_small_hours_belong_to_the_previous_day_night(tmp_path):
    """A consequence of defining the night as 23:00 → 06:00 the next day.

    Half an hour of screen at 00:20 on day 1 is counted in day 0's night, not
    day 1's. It is the right convention (it is the same night), but it has an
    edge: the small hours of the **first** day of the period belong to a night
    that predates the data and are therefore counted in no row.
    """
    df = _frame(_full_day(0) + [
        ev("SCREEN_ON", 1, "00:20", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "00:20:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:50"),
    ] + _full_day(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_min"] == 30, "attributed to day 0's night"
    assert df.loc[DAY0 + dt.timedelta(days=1), "night_min"] == 0


def test_last_use_time_does_not_drop_when_going_to_bed_later(tmp_path):
    """The axis shifts to 04:00: the small hours come out as 24 to 28.

    Without this, going to bed at 01:00 registers as `1.0` and the mean "time
    of last screen" *drops* when the user goes to bed later, which is the
    opposite of what happened.
    """
    df = _frame(_full_day(0) + [
        ev("SCREEN_ON", 0, "23:50", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "23:50:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "01:00"),
    ] + _full_day(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_end_h"] == 25.0, "01:00 is expressed as 25:00"


def test_days_truncated_by_the_file_edge_are_excluded(tmp_path):
    """The user_b file ends at 00:46 on the 31st. That day has 0.8 h of
    coverage and averaging it sinks the month's means."""
    df = _frame(_full_day(0) + [
        ev("SCREEN_ON", 1, "00:10", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "00:10:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:40"),
    ], tmp_path=tmp_path)

    assert list(df["day"]) == [DAY0], "day 1 only has 40 min of coverage"
    # but its events do count towards day 0's night
    assert df.loc[DAY0, "night_min"] == 30


def test_app_switches_reset_every_day(tmp_path):
    """Without the reset, the first app of the morning counts as a switch from
    the last one of the night before: one false switch per day."""
    events = []
    for d in (0, 1):
        events += [
            ev("SCREEN_ON", d, "09:00", is_keyguard_locked=True),
            ev("USER_PRESENT", d, "09:00:02", is_keyguard_locked=False),
            ev("APP_FOREGROUND", d, "09:01", package_name="com.whatsapp",
               category="MESSAGING"),
            ev("APP_FOREGROUND", d, "09:03", package_name="com.spotify.music",
               category="ENTERTAINMENT"),
            ev("SCREEN_OFF", d, "09:05"),
        ] + _full_day(d)
    df = _frame(events, tmp_path=tmp_path)

    assert list(df["app_switches"]) == [1, 1], \
        "one switch per day, not two on the second"


def test_longest_disconnection_inside_the_waking_window(tmp_path):
    """Measured only between 07:00 and 23:00: sleeping is no achievement."""
    df = _frame([
        ev("SCREEN_ON", 0, "07:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "07:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "08:00"),
        ev("SCREEN_ON", 0, "14:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "14:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "14:10"),
        ev("SCREEN_ON", 0, "22:55", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "22:55:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "22:59"),
    ], tmp_path=tmp_path)

    # gaps inside the waking window: 08:00→14:00 (6 h) and 14:10→22:55 (8 h 45).
    assert df.loc[DAY0, "longest_offline_s"] == 8 * 3600 + 45 * 60


def test_waking_offline_complements_screen_time(tmp_path):
    """Screen plus offline has to add up to the whole waking window."""
    df = _frame(_full_day(0), tmp_path=tmp_path)
    window_s = (WAKE_END - WAKE_START) * 3600
    row = df.loc[DAY0]
    assert abs(row["screen_wake_s"] + row["offline_wake_s"] - window_s) < 1


def test_daily_screen_time_is_exactly_the_sum_of_its_stretches(tl_a, df_a):
    """Invariant over the real data: the day row is the sum of its stretches."""
    per_day = {}
    for iv in tl_a.intervals:
        per_day[iv.day] = per_day.get(iv.day, 0) + iv.seconds
    for day, screen_s in zip(df_a["day"], df_a["screen_s"]):
        assert abs(per_day[day] - screen_s) < 1e-6


def test_pickups_plus_glances_equal_the_screen_ons(tl_a):
    """Every SCREEN_ON ends up classified, none lost and none duplicated."""
    n_on = sum(1 for e in tl_a.events if e["event_type"] == "SCREEN_ON")
    classified = sum(i.pickups + i.glances for i in tl_a.intervals)
    orphans = tl_a.anomalies.get("USER_PRESENT with no SCREEN_ON", 0)
    assert classified - orphans == n_on


def test_short_weeks_are_flagged(df_b):
    w = weekly_frame(df_b)
    assert w.loc[w["days"] == 7, "is_partial"].eq(False).all()
    assert w.loc[w["days"] < 7, "is_partial"].all()


def test_loading_is_deterministic(tmp_path):
    """Same file, same result: the derivation is a pure function of the event
    log, with no external state and no dependency on execution time."""
    from balance.events import load
    from conftest import DATA
    a = daily_frame(load(DATA / "events_user_a.json", "A"))
    b = daily_frame(load(DATA / "events_user_a.json", "A"))
    pd.testing.assert_frame_equal(
        a.drop(columns=["_cat_s", "_app_s", "_site_s"]),
        b.drop(columns=["_cat_s", "_app_s", "_site_s"]))


def test_the_longest_stretch_records_when_it_starts(tmp_path):
    """Context, not just duration: "your longest break was Saturday afternoon".
    Without the when, a stretch is only a number."""
    # 1 May 2026 is a Friday; the 2nd is a Saturday.
    df = _frame(_full_day(1) + [
        ev("SCREEN_ON", 1, "10:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "10:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "10:05"),
        ev("SCREEN_ON", 1, "17:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "17:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "17:05"),
    ], tmp_path=tmp_path)

    row = df.iloc[0]
    assert row["longest_offline_when"] == "Saturday morning"
    assert row["longest_offline_h"] == pytest.approx(6.92, abs=0.02)


def test_the_time_bands_are_not_off_by_one():
    """The band limit is the upper bound: hour 3 is early morning, not morning.

    The list this was translated from was misaligned and labelled 03:00 as
    "morning" and 10:00 as "midday".
    """
    from balance.metrics import _when
    from conftest import ts
    assert _when(ts(0, "03:00")).endswith("early morning")
    assert _when(ts(0, "10:00")).endswith("morning")
    assert _when(ts(0, "13:00")).endswith("midday")
    assert _when(ts(0, "17:00")).endswith("afternoon")
    assert _when(ts(0, "22:00")).endswith("evening")


def test_the_when_of_the_stretch_is_never_missing_in_real_data(df_a, df_b):
    for df in (df_a, df_b):
        assert df["longest_offline_when"].notna().all()
        assert df["longest_offline_h"].gt(0).all()
