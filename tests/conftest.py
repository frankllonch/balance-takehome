"""
Shared test helpers.

Most tests build synthetic streams by hand instead of using the data files: a
test that depends on the real data only says "today this comes out", while a
synthetic one says "this rule does this". The real files are used only in
`test_data_contract.py`, where the data *is* the subject of the test.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from balance.events import Timeline, load

DATA = Path(__file__).resolve().parents[1] / "data"

#: Base day for synthetic streams. Any would do; one is fixed so the tests are
#: deterministic and dates can be written by hand.
DAY0 = dt.date(2026, 5, 1)


def ts(day_offset: int, clock: str) -> int:
    """`ts(0, "23:50")` → epoch millis of that instant on the base day.

    The device clock arrives normalised to UTC, so it is built the same way
    here: no local timezone in the middle.
    """
    h, m, *rest = (int(x) for x in clock.split(":"))
    sec = rest[0] if rest else 0
    moment = dt.datetime.combine(
        DAY0 + dt.timedelta(days=day_offset),
        dt.time(h, m, sec), tzinfo=dt.timezone.utc)
    return int(moment.timestamp() * 1000)


def ev(kind: str, day_offset: int, clock: str, **extra) -> dict:
    """An event with the eight schema fields, the non-applicable ones at None."""
    base = {
        "id": 0, "event_type": kind, "timestamp_millis": ts(day_offset, clock),
        "package_name": None, "url_domain": None, "category": None,
        "block_type": None, "is_keyguard_locked": None,
    }
    base.update(extra)
    return base


def build(events: list[dict], user: str = "T", tmp_path: Path | None = None) -> Timeline:
    """Builds a `Timeline` from an in-memory list of events.

    It writes a temporary JSON instead of calling the internals, so the test
    walks exactly the same path as production (`load`).
    """
    import json
    for i, e in enumerate(events):
        e["id"] = i
    path = (tmp_path or Path("/tmp")) / f"events_{user}.json"
    path.write_text(json.dumps(events))
    return load(path, user)


@pytest.fixture(scope="session")
def tl_a() -> Timeline:
    return load(DATA / "events_user_a.json", "A")


@pytest.fixture(scope="session")
def tl_b() -> Timeline:
    return load(DATA / "events_user_b.json", "B")


@pytest.fixture(scope="session")
def df_a(tl_a):
    from balance.metrics import daily_frame
    from balance.score import add_score
    return add_score(daily_frame(tl_a))


@pytest.fixture(scope="session")
def df_b(tl_b):
    from balance.metrics import daily_frame
    from balance.score import add_score
    return add_score(daily_frame(tl_b))
