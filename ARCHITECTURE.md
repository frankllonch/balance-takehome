# Architecture

A document for whoever has to **change** this, not for whoever has to assess it.
The product reasoning and the findings are in [`README.md`](README.md); the
shape of the input files is in [`INPUT_FORMAT.md`](INPUT_FORMAT.md).

---

## 1 · The idea in one sentence

The event file is the **system of record**: immutable, the single source of
truth. Everything else (screen stretches, daily metrics, index, alerts) is
**derived data**: a pure, deterministic function of that log. Nothing is half
stored, nothing depends on the execution clock, and deleting any derivative and
recomputing it returns exactly the same thing.

Two rules follow, and neither is worth breaking:

1. **One derivation, one owner.** If two places compute the same thing, sooner
   or later they disagree. `daily_frame` assigns the week; nobody else
   recomputes it.
2. **A core with no framework.** `events`, `metrics`, `score` and `intelligence`
   import neither Streamlit nor Plotly. The dashboard and the CLI are adapters,
   which is why they can be tested separately and cannot drift apart.

---

## 2 · Layers

```
data/*.json          event log · system of record · immutable
       │
       ▼
balance/events.py    LAYER 0 · reconstruction
                     · screen state machine (depth counter)
                     · pickups against glances
                     · time attribution to app and to domain
                     → Timeline(intervals, usages, blocks, anomalies)
       │
       ▼
balance/metrics.py   LAYER 1 · aggregation
                     · daily_frame(): one row per day, ~65 columns
                     · weekly_frame(): one row per week, with changes
                     · totals(), category_daily(), hourly_heat(), blocks_frame()
       │
       ▼
balance/score.py     LAYER 2 · 0 to 100 index
                     · five weighted components + breakdown
       │
       ▼
balance/intelligence.py  LAYER 3 · decision
                     · guardian alert rules with a silence budget
                     · reinforcement rules (user and guardian) with a weekly quota
                     · night nudge + replay over history
                     · month_replay(): system state day by day
       │
       ├──────────────┬──────────────────────────
       ▼              ▼
balance/run.py    app.py + balance/charts.py + balance/theme.py
CLI               Streamlit dashboard
```

`charts.py` and `theme.py` are pure presentation: they receive frames already
computed and decide nothing.

---

## 3 · Invariants

The tests pin them; if you touch the code and one falls, that is a product
decision, not a detail to fix quietly.

| Invariant | Where it is tested |
|---|---|
| Every `SCREEN_ON` ends up classified as pickup or glance, none lost or duplicated | `test_metrics.py` |
| A day's screen time is the exact sum of its stretches | `test_metrics.py` |
| Waking screen time + waking offline = the waking window | `test_metrics.py` |
| Blocks by type sum to the total | `test_data_contract.py` |
| The index sits in [0, 100] and its weights sum to 1 | `test_score.py` |
| Making an input worse never raises the index | `test_score.py` |
| Blocks do **not** affect the index | `test_score.py` |
| The guardian payload contains no apps, domains or categories | `test_intelligence.py` |
| The walkthrough only uses information prior to each date | `test_intelligence.py` |
| Loading the same file twice gives the same frame | `test_metrics.py` |
| CLI and dashboard compute the same thing | `test_cli.py` |

---

## 4 · Decisions that look arbitrary and are not

Each one is commented where it lives, and each one has a test.

- **Depth counter for the screen.** The log overlaps sessions and does not say
  which OFF closes which ON. The union of stretches does not depend on that
  choice; any pairing does, and it deviates in both directions.
- **Two day conventions.** The calendar day cuts at midnight; the night runs
  23:00 to 06:00 the next day, because sleep does not cut at midnight.
- **Hour axis shifted to 04:00.** The small hours are expressed as 24 to 28.
  Without it, the mean "time of last screen" *drops* when someone goes to bed
  later.
- **Truncated days out.** A day the file only partly covers does not enter
  averages, rankings or charts, but its events do count towards the previous
  day's night.
- **App switches reset every day**, or the first app of the morning counts as a
  switch from the last one of the night.
- **Time bands are labelled by upper bound.** Hour 3 is early morning, not
  morning. The list was off by one at one point and the test now pins it.

---

## 5 · How to make the likely changes

### Add a daily metric

In `metrics.py`, inside the `rows.append({...})` of `daily_frame`. If it is
derivable from columns that already exist, compute it in `add_score` or in the
layer that uses it: `daily_frame` walks events and should keep only what that
walk needs.

### Add an alert rule

1. Write `_my_rule(df) -> list[Signal]` in `intelligence.py`.
2. Add it to `RULES`.
3. Set `actionability` with judgement: below 0.5 it is never notified, it goes
   to the weekly summary. That is the lever deciding what deserves an
   interruption.
4. Add the test pinning the date it fires and the one it does not.

### Add a reinforcement rule

The same, but in `POSITIVE_RULES`, returning through the `_pos(...)` helper.
Three conditions before writing it:

- it compares against the user's **own history**, not a fixed threshold;
- it demands margin (10 % on records, 20 to 30 % on weekly aggregates);
- the text describes, it does not recommend. A test catches imperatives.

### Change the index weights

`COMPONENTS` in `score.py`. The bounding and monotonicity tests do not depend on
the calibration, so they will keep passing; the ones in
`test_data_contract.py` citing concrete figures will not, and that is
deliberate: if a recalibration changes what the dashboard claims, the test says
so before the reader does.

### Add a profile

`PROFILES` in `run.py` and `HAS_GUARDIAN` in `app.py`. In production this would
come from the account; today they are two constants because there are two files.

---

## 6 · Known limits

- **One month of data.** The weekly rules need 2 to 3 weeks of reference, so the
  first two weeks of any new profile generate nothing.
- **The drift detector uses a rolling reference**, so it stops firing once the
  new behaviour becomes the normal one. That is right for alerting once, but its
  silence does not mean "resolved".
- **The small hours of the first day** of the period belong to a night that
  predates the data and are counted in no row.
- **Attribution coverage does not reach 100 %** (86 % in A, 67 % in B): the rest
  is lock screen, home screen and notifications.
- **Everything fits in memory.** With 11,488 events that is plenty; with a year
  of a million users, `daily_frame` would become a per-day incremental aggregate
  on the device, which is where it should live anyway.

---

## 7 · Commands

```bash
make install    # environment + dependencies
make test       # 94 tests
make run        # console analysis
make json       # the same analysis as JSON
make csv        # daily and weekly frames into out/
make dash       # dashboard at http://localhost:8501
```
