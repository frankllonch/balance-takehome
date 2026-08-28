"""
The CLI as proof the engine exists outside the interface.

If the only way to see the results were the dashboard, there would be no way to
tell an engine that computes from a screen with hand-written numbers. These
tests exercise the same path a nightly cron would.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from balance.run import PROFILES, analyse, render_json, render_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=list(PROFILES))
def result(request):
    return analyse(request.param, ROOT)


def test_the_analysis_is_a_pure_function_of_the_log():
    """Same file, same result: no external state and no clock."""
    a = render_json(analyse("B", ROOT))
    b = render_json(analyse("B", ROOT))
    assert a == b


def test_the_text_output_mentions_every_section(result):
    text = render_text(result)
    for section in ("PERIOD AVERAGES", "BY WEEK", "GUARDIAN ALERTS",
                    "REINFORCEMENTS", "NIGHT NUDGE", "EMISSIONS IN THE PERIOD"):
        assert section in text


def test_the_json_is_serialisable_and_free_of_numpy_types(result):
    """`json.dumps` without `default=` only passes if everything is native."""
    raw = json.dumps(render_json(result), ensure_ascii=False)
    back = json.loads(raw)
    assert back["user"] == result["user"]
    assert isinstance(back["averages"]["screen_min"], float)


def test_a_profile_without_a_guardian_emits_no_digest(result):
    j = render_json(result)
    if not j["has_guardian"]:
        assert j["guardian_digest"] is None
        assert all(p["audience"] == "user" for p in j["positives"])


def test_the_cli_actually_starts():
    """Run as a subprocess: covers `argparse` and `__main__`."""
    r = subprocess.run(
        [sys.executable, "-m", "balance.run", "--user", "A", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data[0]["user"] == "A"
    assert data[0]["days"] == 30


def test_the_csv_dump_writes_both_frames(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "balance.run", "--user", "B",
         "--format", "json", "--csv", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "daily_B.csv").exists()
    assert (tmp_path / "weekly_B.csv").exists()


def test_the_cli_and_the_dashboard_compute_the_same_thing():
    """The two interfaces are adapters over the same core, not two
    implementations that can drift apart."""
    from balance.events import load
    from balance.intelligence import evaluate_alerts
    from balance.metrics import daily_frame
    from balance.score import add_score

    direct = add_score(daily_frame(load(ROOT / "data/events_user_b.json", "B")))
    via_cli = analyse("B", ROOT)["daily"]
    assert direct["score"].tolist() == via_cli["score"].tolist()
    assert ([s.key for s in evaluate_alerts(direct)]
            == [s.key for s in analyse("B", ROOT)["alerts"]])
