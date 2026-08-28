"""
Layer 0: screen reconstruction, sessions and time attribution.

This is the layer that decides whether everything above it is true, and the
only one dealing with a stream that does not arrive clean. Every odd case seen
in the real files has its synthetic test here.
"""

from __future__ import annotations

import datetime as dt

from balance.events import MAX_FOREGROUND_S
from conftest import DAY0, build, ev, ts


def test_a_pickup_is_an_unlock(tmp_path):
    """ON followed by USER_PRESENT is a real unlock, not a glance."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:05", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:10"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].pickups == 1
    assert tl.intervals[0].glances == 0
    assert tl.intervals[0].seconds == 600


def test_a_screen_on_without_unlock_is_a_glance(tmp_path):
    """ON with no USER_PRESENT is a glance: the screen came on, the phone was
    never opened."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:00:12"),
    ], tmp_path=tmp_path)

    assert tl.intervals[0].pickups == 0
    assert tl.intervals[0].glances == 1
    assert tl.intervals[0].is_pickup is False


def test_overlapping_stretches_are_a_single_interval(tmp_path):
    """The case that breaks naive pairing.

    ON(09:00) ON(09:04) OFF(09:06) OFF(09:11) shows up 77 times in user_a and
    411 in user_b. Pairing them off gives 2+5=7 minutes; physically the screen
    was on from 09:00 to 09:11, which is 11.
    """
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("SCREEN_ON", 0, "09:04", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:04:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:06"),
        ev("SCREEN_OFF", 0, "09:11"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1, "the union is one stretch, not two"
    assert tl.intervals[0].seconds == 11 * 60
    assert tl.intervals[0].pickups == 2, "both unlocks still count"


def test_two_ons_without_unlock_are_two_glances(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_ON", 0, "09:01", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:02"),
        ev("SCREEN_OFF", 0, "09:03"),
    ], tmp_path=tmp_path)

    assert tl.intervals[0].glances == 2
    assert tl.intervals[0].pickups == 0


def test_user_present_without_screen_on_opens_a_stretch(tmp_path):
    """A stretch is opened and the anomaly is recorded rather than dropped."""
    tl = build([
        ev("USER_PRESENT", 0, "09:00", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:05"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].seconds == 300
    assert tl.anomalies["USER_PRESENT with no SCREEN_ON"] == 1


def test_screen_off_while_already_off_is_ignored(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:05"),
        ev("SCREEN_OFF", 0, "09:06"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.anomalies["SCREEN_OFF while screen already off"] == 1


def test_a_stretch_crossing_midnight_is_split(tmp_path):
    """Daily screen time has to add up to exactly that day."""
    tl = build([
        ev("SCREEN_ON", 0, "23:40", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "23:40:05", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:20"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 2
    a, b = tl.intervals
    assert a.day == DAY0 and b.day == DAY0 + dt.timedelta(days=1)
    assert a.seconds == 20 * 60 and b.seconds == 20 * 60
    assert a.pickups == 1 and b.pickups == 0, \
        "the unlock belongs to the day it happened on"


def test_file_ending_with_the_screen_on(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.anomalies["stretch left open at end of file"] == 1
    assert tl.intervals[0].end_ms == ts(0, "09:01")


# ---------------------------------------------------------------------------
# Time attribution
# ---------------------------------------------------------------------------

def test_app_time_runs_to_the_next_foreground(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("APP_FOREGROUND", 0, "09:04", package_name="com.spotify.music",
           category="ENTERTAINMENT"),
        ev("SCREEN_OFF", 0, "09:10"),
    ], tmp_path=tmp_path)

    per_app = {u.key: u.seconds for u in tl.usages}
    assert per_app["com.whatsapp"] == 3 * 60
    assert per_app["com.spotify.music"] == 6 * 60


def test_the_domain_takes_the_time_off_the_browser(tmp_path):
    """Chrome is a container, not a destination: the time goes to the domain."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:00:10", package_name="com.android.chrome",
           category="OTHER"),
        ev("URL_VISIT", 0, "09:01", url_domain="bbc.com", category="NEWS"),
        ev("SCREEN_OFF", 0, "09:06"),
    ], tmp_path=tmp_path)

    per_key = {u.key: u.seconds for u in tl.usages}
    assert per_key["com.android.chrome"] == 50
    assert per_key["bbc.com"] == 5 * 60


def test_events_with_the_screen_off_generate_no_time(tmp_path):
    """Background music and sync. Never happens in the two sample files; the
    guard is there because a real device does produce them."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:05"),
        ev("APP_FOREGROUND", 0, "09:30", package_name="com.spotify.music",
           category="ENTERTAINMENT"),
    ], tmp_path=tmp_path)

    assert tl.usages == []
    assert tl.anomalies["APP_FOREGROUND with screen off"] == 1


def test_a_block_closes_the_foreground_but_consumes_no_time(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("BLOCK", 0, "09:03", package_name="com.instagram.android",
           category="SOCIAL_MEDIA", block_type="APP"),
        ev("SCREEN_OFF", 0, "09:05"),
    ], tmp_path=tmp_path)

    assert {u.key for u in tl.usages} == {"com.whatsapp"}
    assert tl.usages[0].seconds == 2 * 60
    assert len(tl.blocks) == 1
    assert tl.blocks[0].block_type == "APP"


def test_foreground_cap(tmp_path):
    """If the SCREEN_OFF is missing, an app cannot pile up hours."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("SCREEN_OFF", 0, "23:00"),
    ], tmp_path=tmp_path)

    assert tl.usages[0].seconds == MAX_FOREGROUND_S


def test_events_are_sorted_even_if_they_arrive_out_of_order(tmp_path):
    """The format promises time order, but `load` does not take it on trust."""
    tl = build([
        ev("SCREEN_OFF", 0, "09:10"),
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].seconds == 600
