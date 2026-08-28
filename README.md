# Balance · take-home

From a device event log to metrics, a wellbeing index, guardian alerts and
user reinforcements.

```bash
make install    # environment and dependencies
make test       # 94 tests
make run        # analyse both profiles on the console
make dash       # dashboard
```

| Document | For what |
|---|---|
| This one | what I found in the data and why I decided what I decided |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | how it is put together and how to change it |
| [`INPUT_FORMAT.md`](INPUT_FORMAT.md) | the shape of the input files |

All four phases of the exercise are built, with a CLI and 94 tests. What I left
out on purpose is in section 9; what I would do with more time, in section 10.

---

## 1 · What is in the data

| | User A | User B |
|---|---|---|
| Events | 2,941 | 8,547 |
| Complete days | 30 (1 to 30 May) | 30 (1 to 30 May) + tail of the 31st |
| Screen per day | 2 h 02 min | 4 h 22 min |
| Real unlocks per day | 19 | 45 |
| Glances without opening, per day | 4.4 | 4.4 |
| Distinct apps per day | 6.7 | 12.7 |
| App switches per screen hour | 9.4 | 16.8 |
| Offline while awake (07:00 to 23:00) | 14.0 h | 12.1 h |
| Screen 23:00 to 06:00 | **0.0 min across 30 days** | 30 min on average |
| Blocked attempts | 53 | 1,167 |
| Of those, ADULT / GAMBLING | 0 | 203 |
| On-device nudity detections | 0 | 43 |

**A is an adult; B is a minor with a guardian.** Not because the brief says so,
because the behaviour does: B uses Duolingo and Kindle daily, keeps three
messaging apps in parallel, *tries* to open Roblox (75 attempts, the filter lets
2 through) and Clash of Clans (71 attempts, 0 through), and produces
`ADULT`/`GAMBLING` categories that never appear once in A. That decides the rest
of the design: **for A the product is already working and the right move is to
stay quiet; for B there is a story to tell, and a decision to make about which
part of it belongs to the guardian.**

## 2 · The finding

B's volume of use barely changes; their schedule does. Between week 1 and week 4:

| | Week 1 | Week 4 | Δ |
|---|---|---|---|
| Screen per day | 244 min | 265 min | **+8 %** |
| Unlocks per day | 43 | 44 | +3 % |
| Late-night minutes | 4.4 | 59.2 | **×13** |
| Unlocks after midnight | 0.6 | 9.3 | **×16** |
| Last screen (mean) | 23:21 | 01:06 | **+105 min** |
| First unlock (mean) | 08:43 | 08:54 | +10 min |
| Sleep window | 9.4 h | 7.8 h | **−95 min** |

Bedtime slides 105 minutes later and wake-up time holds, so the whole shift
comes out of available rest. A rule on screen time would not have caught this
case: volume rises 8 % while the night band multiplies by 13.

A records **0.0 minutes** of night-band screen across 30 days. The 23:00 cut is
not an arbitrary threshold in the score: some people respect it on their own, so
penalising it separates rather than punishing everyone.

**Sensitive content: a spike, not a trend.** B's 203 adult and gambling attempts
are not a trend: 145 of the 203 (71 %) fall in weeks 2 and 3, and drop to 30 in
week 4. Persistence is low: grouped into 10-minute bursts they average **1.2
attempts, 3 at most**. That is someone trying, hitting the block and giving up,
not insistence on the same content. It determines where the signal goes: weekly
summary, not notification.

**The filter steps in less and less for A.** Blocks fall from 19 in week 1 to 3
in week 4, and the distraction share from 19 % to 15 %. The wall intervenes less
because the opening habit moved, not because the barrier is holding harder. A's
screen time is the same as on day one, so this signal appears in no volume
metric.

**Category split, no relevant difference:** B's mean distraction share (17.5 %)
is practically A's (15.5 %). B's problem is not the category split, it is total
volume, timing, and the number of blocked attempts along the way.

## 3 · Engineering decisions (the data is not clean)

1. **Screen stretches overlap.** 77 `SCREEN_ON` in A and 411 in B fire while the
   screen is already on, balanced later by consecutive `SCREEN_OFF`. The data
   does not say which OFF closes which ON, and choosing wrong changes the result
   **in both directions**. Over user A:

   | Strategy | Hours | Against the union |
   |---|---|---|
   | Union (depth counter) | **61.1** | — |
   | LIFO stack | 64.9 | +6 %, counts the overlap twice |
   | FIFO queue | 56.7 | −7 %, loses the trailing stretch |
   | Restart the clock on every ON | 53.0 | −13 % |

   The screen is modelled as a depth counter (ON adds, OFF subtracts; on while
   > 0), which returns the **union** of the stretches. The union does not depend
   on the pairing chosen, and it is what "the screen was on" means. In B the
   spread runs from 93.4 h to 155.1 h against 131.1 for the union.
2. **Days truncated by the file edge.** B runs to 00:46 on the 31st. That day is
   excluded from averages, rankings, the heatmap and blocks; its events do count
   towards the night of the 30th. Without the filter, B's mean screen time drops
   from 261.8 to 253.7 min.
3. **Two day conventions, on purpose.** The calendar day cuts at midnight. The
   **night** runs 23:00 on day D to 06:00 on D+1, because sleep does not cut at
   midnight and splitting one night across two rows destroys the signal that
   matters. Known edge: the small hours of the first day of the period belong to
   a night that predates the data and are counted nowhere.
4. **The first unlock needs a floor.** With the day cutting at midnight, a day
   starting at 00:20 (the tail of the previous night) registers as "the day
   started at 00:20". It is defined as the first unlock **from 06:00 onwards**.
5. **Time per domain, not per browser.** A `URL_VISIT` takes the time off Chrome
   and the domain keeps it. That is why Chrome shows 115 openings and 12 minutes
   in A: it is a container, not a destination.
6. **Real pickup vs glance:** a `SCREEN_ON` with a `USER_PRESENT` before the next
   ON/OFF. A: 573 pickups and 133 glances over 706 `SCREEN_ON`. B: 1,349 and 131
   over 1,480.
7. **App switches reset every day.** Without that, the first app of the morning
   counts as a switch from the last one of the night: 0.83 false switches a day
   on both profiles (4.1 % of the total in A, 1.1 % in B).
8. **Guards that never trigger on these files:** events with the screen off,
   orphan `USER_PRESENT`, and the 45-minute foreground cap (the longest stretch
   observed is 32.6 min). They are in the code because a real device produces
   them. The one anomaly that does appear is 4 duplicate `USER_PRESENT` inside a
   stretch in A and 6 in B.

Coverage: 86 % of A's screen time and 67 % of B's is attributed to an app or a
site. The rest is lock screen, home screen and notifications, and B's being
lower is consistent with their pattern of frequent wake-ups.

## 4 · The wellbeing index (0 to 100)

| Component | 100 at | 0 at | Weight |
|---|---|---|---|
| Screen time | ≤ 90 min | ≥ 360 min | 25 % |
| Fragmentation (unlocks) | ≤ 15 | ≥ 60 | 20 % |
| Protected night (min 23:00 to 06:00) | 0 | ≥ 60 | 20 % |
| Longest disconnection while awake | ≥ 4 h | ≤ 1 h | 15 % |
| Intent (distraction share) | ≤ 10 % | ≥ 50 % | 20 % |

Result: **A 83** (82 → 82 between week 1 and week 4), **B 48** (60 → 41, dragged
down by the night).

**Absolute anchor, personal narrative.** The number is measured against fixed
bands; the comparison against oneself (rolling 14-day median) sits beside it,
not inside it. If the score were relative, someone doing a constant 6 h/day
would score 100 for being constant.

**Blocks do not score, on purpose.** A `BLOCK` means the phone did its job and
the content never opened. Penalising the attempt punishes someone for an impulse
the product already handled, and creates the incentive to turn the protection
off to raise the grade.

**Why the night carries 20 % while being the smallest metric.** 60 minutes at
01:00 and 60 at 17:00 do not cost the same, and it is the cheapest lever: asking
for two hours less a day is asking for a change of life; asking to put the phone
down 40 minutes earlier is asking for one thing.

### Where it breaks

- **The same bands for everyone.** A teenager and an adult working from home
  should not be measured alike. With more time: calibrate per cohort, or move to
  a personal percentile after 30 days of baseline.
- **It punishes the legitimately heavy user.** Someone using the phone for work
  scores badly without doing anything wrong. A notion of "purposeful use" is
  missing.
- **The distraction share only sees what actually opened.** B's most problematic
  categories never appear in their mix because the phone never let them open, so
  B's intent score comes out artificially good (81/100).
- **One number hides the variance.** B and someone with the same mean
  concentrated into two binges score the same.
- **It is gameable.** Turning the screen off and on again changes nothing, but a
  determined user can optimise the metric without changing the habit.

## 5 · Alerts and nudges (`balance/intelligence.py`)

### The guardian alert: a regime change, not a threshold

Three rules run over the month. The third is there deliberately as a **negative
control**:

| Rule | What it watches | Does it fire? |
|---|---|---|
| `night_drift` | median of 5 nights against the previous 14, plus the delay in lights-out | **B: 19 May**. A: never |
| `sensitive_spike` | sensitive attempts over 7 days against the previous rate | B: 14 May. A: never |
| `screen_jump` | "screen time has gone up a lot" | **never, on either profile** |

`screen_jump` not firing is the result, not a gap: it is the rule almost anyone
would implement, and on this data it would have missed the only thing that was
happening. B's daily use rises 8 % while their night schedule multiplies by 13.

`night_drift` fires on **19 May**, twelve days before the file ends and long
before any volume metric shows anything. It stops holding on the 23rd because
the rolling reference absorbs the new behaviour. For alerting that is right (you
report **the change**, once); but it is worth saying out loud that **the
detector going quiet does not mean "fixed"**. The absolute level is still
carried by the index and the weekly summary, which have no short memory.

### The silence budget

The real failure mode of a notification channel aimed at a parent is not missing
an event: it is shouting until they stop reading. So there is a **quota of 2
alerts per 30 days** and a minimum gap of 10 days, and every candidate is ranked
by `magnitude × persistence × actionability` (a product, not a sum: something
huge but one day long, or persistent but not actionable, should not sneak
through).

In B, `sensitive_spike` **is detected and not sent**. Its actionability is 0.35
on purpose: the phone already blocked all 203 attempts, none opened, and the
conversation left does not improve by arriving today rather than on Sunday. It
drops to the weekly summary. Interrupting a parent for this burns the channel's
credibility for when it is genuinely needed.

The dashboard lists the held signals with their reason.

### The nudge, measured before sending it

Rule: the second reopening from 23:30 onwards, once per night. Silences: a
single reopening is not a pattern; and if the last few nights are already better
than their own median, stay quiet.

You cannot A/B test a closed file, but you can **replay the rule over history**:

| | User A | User B |
|---|---|---|
| Nights with a nudge | **0 of 30** | 14 of 30 (47 %) |
| Night minutes this month | 0 | 905 |
| Minutes after the trigger | 0 | **348 (38 %)** |
| Per nudged night | n/a | ~25 min |

348 minutes is the **ceiling** of what the nudge can recover, not what it will;
it tells you whether the rule points at something with headroom before spending
an interruption on it. The annoyance cost is measured in the other direction:
zero triggers across A's 30 nights, with no configuration.

### Context, not just figures

A number has to mean something. The comparison against oneself was there from
the start (rolling 14-day median); the **when** of the longest stretch was not,
and the duration was computed without keeping the moment. Now
`longest_offline_when` gives the phrase ("Saturday morning") and it appears in
the daily rhythm, the weekly summary and the day detail.

### Month walkthrough (how it is shown to work)

The "Alerts and nudges" tab opens with a slider walkthrough: **one chart with
the seven variables the rules read**, switchable from the legend, over the same
timeline where alerts, reinforcements and nudges are marked.

Seven magnitudes on one axis need a common transform. Each series runs as a
**percentage of its own maximum for the period**: not a disguised second scale,
a single scale with a declared transform, and the real value with its unit
travels in the tooltip. It divides by the maximum rather than rescaling min-max
because zero has to stay zero: for user A, "zero late-night minutes" is the
data, and min-max would paint it halfway up.

Three series start on and the other four come in with a click. The legend is
grouped into "Watched variables" and "Emissions", but with
`groupclick="toggleitem"`: the group is only a title and each entry toggles on
its own.

Below zero sits an **event rail** with what the phone emitted each day. It
shares the time axis with the data that explains it: the 19 May alert sits right
above the rise in late-night use that causes it.

Rules are **re-evaluated with the history available up to each date**, not the
whole month (`month_replay`): the phone on the 12th did not know what would
happen on the 19th, and neither does the walkthrough.

Below, the outputs for that date. **Only the ones that exist are drawn**: if
there is no notification there is a gap reading "no notifications", and the
guardian column does not appear on profiles without a guardian.

Emissions over the month:

| Destination | User A | User B |
|---|---|---|
| Nudge on screen | 0 | 14 |
| Reinforcement to the user | 3 | 1 |
| Guardian notification | no guardian | 1 |
| Reinforcement to the guardian | no guardian | 1 |
| Weekly summary entry | no guardian | 1 |
| **Total over 30 days** | **3** | **18** |

## 6 · Positive reinforcement

A system that only speaks when something gets worse reads as a threat, and user
A proves it: with the alert rules alone, a healthy profile receives **zero**
information about their own use in 30 days.

### Criteria

Three design rules before the six detection rules:

1. **Against yourself, not against a table.** An absolute threshold always
   congratulates A and never B, the exact opposite of useful.
2. **Only with margin.** 10 % over the best recent record, 30 % on weekly
   aggregates. A record beaten by one minute is variance.
3. **Descriptive, never prescriptive.** The text says what happened and what it
   is compared against. There is a test that catches imperatives.

| Rule | What it measures | Threshold | Destination |
|---|---|---|---|
| `offline_record` | best screen-free stretch | +10 % over the best of the previous 14 days, minimum 3 h | user |
| `night_streak` | consecutive nights with no screen 23:00 to 06:00 | milestones at 7, 14 and 30 | user |
| `calm_week` | daily filter interventions | 30 % below the previous two weeks | user |
| `focus_week` | share of time in social, entertainment and games | 20 % below the previous week | user |
| `best_week` | weekly index | highest in the history, with 3 previous weeks | user |
| `filter_calm` | attempts towards sensitive content | 40 % below the previous week, starting from 10 or more | guardian |

Quota: **one reinforcement per week and audience**. What does not fit is not
discarded, it drops to the weekly summary.

### What actually fires

| | User A | User B |
|---|---|---|
| Reinforcements to the user | 3 (7, 14 and 28 May) | 1 (28 May) |
| Reinforcements to the guardian | no guardian | 1 (28 May) |
| Recorded but not notified | 3 | 0 |
| Alerts | 0 | 1 |

**A** gets the 7 and 14 protected-night milestones and the week the filter goes
from 2.1 to 0.4 interventions a day. One every ten days on average.

**B** gets one: in week 4 their distraction share falls from 20 % to 16 %. And
their guardian gets `filter_calm`, because sensitive attempts fall from 73 to 30
between weeks 3 and 4. That is the point: B's guardian receives **one alert and
one reinforcement** in the same month, not only bad news.

`best_week` and `offline_record` fire on A but drop to the summary on quota,
which is the proof that the budget does something.

### Short weeks

No weekly rule evaluates weeks under 5 days. Week 5 of the period has 2 or 3
days and would come out artificially good on almost everything; the weekly
summary flags it with an asterisk.

## 7 · Weekly summary

Its own tab, with a week selector and a profile selector. It reuses the existing
metrics aggregated by week: KPIs with the change against the previous week,
week-by-week evolution of the four main magnitudes, the five index components,
the detail of that week's days against the mean of the previous ones, a
comparison table and everything the phone emitted on those days.

The change is computed by **rounding before subtracting**, so the column matches
the two beside it; and when the change rounds to zero it reads "no change"
rather than "+0", which with a green arrow would say something improved when
nothing moved.

## 8 · The privacy line, concretely

- The per-app, per-site and block views are the **user's own device-side view**.
  They never leave.
- What reaches a guardian is an aggregate with no object and no fine counts:
  *"this week the sensitive-content filter stepped in more than usual"*, never
  *"your child tried to open pornhub.com 31 times"*.
- What is reassuring and safe to say: **203 sensitive attempts, 0 opened**.
  Verified against the stream: there is not a single `URL_VISIT` or
  `APP_FOREGROUND` with category `ADULT` or `GAMBLING` in either file. The block
  is 100 % effective.
- The aggregates go out rounded to quarter hours and multiples of 5 points. A
  fine value ("247 minutes, index 41.3") identifies a specific user and, in a
  30-day series, reconstructs much of the behaviour. At the granularity
  transmitted, the guardian tells apart just as well the only two things they
  need to know: whether the state is normal and whether it has changed.

## 9 · What I left out on purpose

Not the same as "what is missing". These five were possible and I chose not to:

- **A score relative to the user.** Kinder and less comparable. Someone at a
  constant 6 h/day would score 100 for being constant.
- **Penalising blocks in the index.** The easy call, and it would have separated
  the two users better. It creates the incentive to turn the protection off.
- **Notifying the sensitive-content spike.** Detected and held: the filter
  already stopped it, persistence is 1.2 attempts per burst, and the conversation
  left gains nothing from arriving today.
- **App and domain rankings for the guardian.** The flashiest part of the
  analysis and the one that breaks the privacy line. They stay on the device.
- **Screen-time nudges.** Interrupting someone because they have been on the
  phone for three hours changes nothing and spends attention. The one nudge
  implemented attacks the schedule, where the headroom is measurable.

## 10 · What is missing and how I would do it

**A Django slice.** `balance/` is already a framework-free library, with
Streamlit and the CLI as two adapters over it, so Django would be a third. What
I would do differently is turn the privacy line into a contract the code
enforces: two serializers (`DeviceSerializer` / `GuardianSerializer`) and the
non-inversion test, which in this delivery lives in `test_intelligence.py` and
there would be an API test.

**Calibrate per cohort.** Today the index bands and rule thresholds are the same
for an adult working from home and a teenager. With more data they get
calibrated per cohort, or moved to a personal percentile after 30 days of
reference.

**Detect binges.** The mean hides the variance: someone with B's mean
concentrated into two nights gets the same index. 95th percentile of session
duration.

**Intervention decay.** A's blocks fall from 19 to 3 per week. That is not a user
metric, it is Balance's business metric: how fast the phone stops having to
intervene. It is in the data and in the CLI, but it has no view of its own.

**Incremental computation.** Everything is recomputed from the whole log on
every run, which is plenty for 11,488 events and makes the result trivially
reproducible. At real volume, `daily_frame` would become a per-day incremental
aggregate computed on the device, which is where it should live anyway.

## 11 · Structure

```
balance/events.py        raw events → intervals, usages and blocks
balance/metrics.py       Timeline → daily and weekly frames
balance/score.py         daily frame → 0 to 100 index + breakdown
balance/intelligence.py  daily frame → alerts with a quota, reinforcements,
                         nudge and the month walkthrough
balance/run.py           CLI (text, JSON, CSV)
balance/charts.py        plotly figures · they decide nothing
balance/theme.py         dark theme, validated palette, device mockup
app.py                   streamlit dashboard (8 tabs)
tests/                   94 tests · layers 0 to 4, CLI and data contract
```

`events`, `metrics`, `score`, `intelligence` and `run` import neither Streamlit
nor Plotly: the core can be computed, tested and put on a cron without the
interface. How to change each piece is in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 12 · On verification

The dashboard makes claims ("77 overlaps", "A's filter falls from 19 to 3", "203
sensitive attempts and none opened"). Each of those has a test in
`tests/test_data_contract.py` that recomputes it by a different path.

It is not decorative: writing those tests uncovered **four published figures
that were wrong**, all inherited from exploratory code using a boolean screen
model instead of the depth counter the code implements. They are corrected; the
detail is in section 3.
