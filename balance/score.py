"""
Layer 2 · a single 0 to 100 number per day.

Five components, each 0 to 100, weighted. The design and its cracks are
explained in the README; the short version:

* **Absolute anchor, personal narrative.** The score is measured against fixed
  bands, not against the user's own past. If it were relative, someone doing a
  constant 6 h/day would score 100 for being constant, and the number would
  stop meaning anything. The comparison against oneself sits *beside* the score
  (`*_delta` in `metrics.py`), not inside it.

* **Blocks do not score.** A BLOCK means the phone did its job: the content
  never opened. Penalising the attempt would punish the user for an impulse the
  product already handled, and would create the wrong incentive (turn the
  protection off to raise your grade). Blocks feed the guardian alert and the
  nudge, not the score.

* **The night carries a lot of weight for how little it takes up.** 60 minutes
  of screen at 01:00 does more damage than 60 minutes at 17:00, and it is far
  easier to correct. It is the lever with the best effort-to-benefit ratio.
"""

from __future__ import annotations

import pandas as pd

#: (column, label, value_scoring_100, value_scoring_0, weight)
COMPONENTS = [
    ("screen_min",        "Screen time",         90,    360,  0.25),
    ("pickups",           "Fragmentation",       15,     60,  0.20),
    ("night_min",         "Protected night",      0,     60,  0.20),
    ("longest_offline_h", "Long disconnection",   4,      1,  0.15),
    ("distract_share",    "Intent",            0.10,   0.50,  0.20),
]

WEIGHTS = {c[0]: c[4] for c in COMPONENTS}
LABELS = {c[0]: c[1] for c in COMPONENTS}


def _band(x: float, good: float, bad: float) -> float:
    """Linear interpolation between `good`→100 and `bad`→0, clamped to [0,100].
    Works in both directions (good < bad and good > bad)."""
    if pd.isna(x):
        return 50.0
    if good < bad:                       # lower is better
        return float(max(0.0, min(100.0, 100 * (bad - x) / (bad - good))))
    return float(max(0.0, min(100.0, 100 * (x - bad) / (good - bad))))


def add_score(df: pd.DataFrame) -> pd.DataFrame:
    """Adds `score` and `score_<component>` to the daily frame."""
    df = df.copy()
    total = pd.Series(0.0, index=df.index)
    for col, _label, good, bad, weight in COMPONENTS:
        s = df[col].map(lambda v: _band(v, good, bad))
        df[f"score_{col}"] = s
        total += s * weight
    df["score"] = total.round(1)

    # 7-day rolling mean: the daily score is noisy, the trend is not.
    df["score_7d"] = df["score"].rolling(7, min_periods=3).mean()
    return df


def contributions(row: pd.Series) -> pd.DataFrame:
    """One day, broken down: how many points each component contributes and how
    many it lets go. This is what makes the score explainable rather than
    magic."""
    return pd.DataFrame([{
        "component": label,
        "raw": row[col],
        "score": row[f"score_{col}"],
        "weight": weight,
        "points": row[f"score_{col}"] * weight,
        "lost": (100 - row[f"score_{col}"]) * weight,
    } for col, label, _g, _b, weight in COMPONENTS])
