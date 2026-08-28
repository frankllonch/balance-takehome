"""
Layer 2: the wellbeing index.

What is tested here is not "the number comes out at 83", which would change
with any recalibration, but the properties the index must hold whatever the
calibration: bounded range, monotonicity in the right direction, weights that
sum to one, and the product decision that blocks do not score.
"""

from __future__ import annotations

import pandas as pd
import pytest

from balance.score import COMPONENTS, _band, add_score, contributions


def test_the_weights_sum_to_one():
    assert abs(sum(w for *_r, w in COMPONENTS) - 1.0) < 1e-9


def test_the_band_interpolates_and_clamps():
    # lower is better
    assert _band(90, 90, 360) == 100
    assert _band(360, 90, 360) == 0
    assert _band(10, 90, 360) == 100, "below the ideal it does not exceed 100"
    assert _band(9999, 90, 360) == 0, "above the worst it does not drop below 0"
    assert _band(225, 90, 360) == pytest.approx(50)
    # higher is better
    assert _band(4, 4, 1) == 100
    assert _band(1, 4, 1) == 0
    assert _band(2.5, 4, 1) == pytest.approx(50)


def test_a_missing_value_does_not_break_the_index():
    """A NaN scores 50, it does not propagate NaN into the total."""
    assert _band(float("nan"), 90, 360) == 50.0


def test_the_index_is_bounded(df_a, df_b):
    for df in (df_a, df_b):
        assert df["score"].between(0, 100).all()


@pytest.mark.parametrize("col,worse", [
    ("screen_min", 600), ("pickups", 200), ("night_min", 300),
])
def test_making_a_metric_worse_lowers_the_index(df_a, col, worse):
    """Monotonicity: if an input gets worse, the index cannot go up."""
    worse_df = add_score(df_a.assign(**{col: worse}))
    assert worse_df["score"].mean() < df_a["score"].mean()


def test_blocks_do_not_score(df_b):
    """A product decision, not an implementation detail.

    A BLOCK means the filter acted and the content never opened. If it docked
    points, the user would have an incentive to turn the protection off to
    raise their grade.
    """
    no_blocks = add_score(df_b.assign(blocks=0, blocks_sensitive=0,
                                      blocks_app=0, blocks_url=0,
                                      blocks_nudity=0))
    pd.testing.assert_series_equal(no_blocks["score"], df_b["score"])


def test_the_breakdown_sums_to_the_index(df_b):
    """The index has to be explainable: contributions add up to the total."""
    row = df_b.iloc[10]
    c = contributions(row)
    assert c["points"].sum() == pytest.approx(row["score"], abs=0.05)
    assert (c["points"] + c["lost"]).sum() == pytest.approx(100, abs=1e-6)


def test_the_components_are_bounded(df_b):
    for col, *_ in COMPONENTS:
        assert df_b[f"score_{col}"].between(0, 100).all()
