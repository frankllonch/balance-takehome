"""
Balance · from a device event log to product decisions.

The event file is the system of record: immutable, the single source of truth.
Everything in this package is derived data, computed as a pure, deterministic
function of that log.

    events  →  metrics  →  score  →  intelligence
     layer 0    layer 1    layer 2      layer 3

None of those four layers imports Streamlit or Plotly. `run.py` (CLI) and
`app.py` (dashboard) are two adapters over the same core, and `charts.py` and
`theme.py` are pure presentation.

See `ARCHITECTURE.md` for the full map and for how to make the usual changes.
"""

__version__ = "1.0.0"
