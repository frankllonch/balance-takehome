# Product Engineer — take-home

Hi, and thanks for taking the time. This exercise is a small, realistic slice of
what you'd actually do on our team. There's no single right answer — we care much
more about how you think than about which framework you pick.

**Time budget:** whatever you need but no need to gold-plate it;
we'd rather see sharp judgment on a smaller surface than an exhausted kitchen sink.

---

## Context

Balance makes a phone that helps people build a healthier relationship with their
device — it blocks distraction, understands how someone actually uses their phone,
and helps keep younger users safer online. Not a dumbphone, not anti-tech: technology
that serves your life instead of hijacking it.

Under the hood, the phone quietly emits a stream of **raw behavioural events** as the
user goes about their day — the screen turns on and off, apps come to the foreground,
the phone blocks a distracting app or an unsafe site, the user visits a page. On its
own that stream is noise. The product's job is to turn it into **meaning**:

```
  raw events  →  daily/weekly metrics  →  a dashboard that says "so what?"
                                       →  alerts & gentle nudges
```

**That whole chain is what this exercise is about.** We give you the raw events;
you turn them into something a person would actually find useful.

---

## The data

`data/events_user_a.json` and `data/events_user_b.json` — one month (30 days) of raw,
on-device events for **two different people**. Each file is a flat, time-ordered JSON
array of event objects. The schema and every field are documented in
[`SCHEMA.md`](SCHEMA.md) — **read it first.**

The two users are **not** the same kind of user. Part of the exercise is noticing how,
and letting that shape what you build. We won't say more than that here.

### A privacy line you must respect

This is a privacy-first product, and that constraint is part of the design problem:

- **Raw events, per-app usage, per-site usage, and what-got-blocked stay on the
  device.** They are the user's own business.
- Only **coarse daily aggregates** (screen time, a wellbeing score, counts, streaks)
  ever leave the device.
- If a user has a **guardian** (think: a parent for a younger user), that guardian is
  **not** a surveillance dashboard. They get **peace of mind** — "things are healthy"
  / "something needs your attention" — never "your kid opened this app 40 times."

Designing *with* this boundary rather than around it is exactly the kind of judgment
we're looking for.

---

## What we'd like you to do

Work through as much of the chain as you can. Roughly in order of importance:

**1. Foundation — turn raw events into metrics.**
Parse the events and compute per-day (and ideally per-week) metrics for each user.
At minimum we'd expect things like: screen time vs offline time, a genuine "pickups"
count (a real unlock, not a passive glance — see `SCHEMA.md`), first pickup, longest
offline stretch, a wind-down / bedtime signal, how many distinct apps and how much
app-switching, blocks (and what kind), and a per-app / per-site picture. Add whatever
else you think matters.

**2. A single wellbeing score.**
Roll the day up into one 0–100 number a user could watch and try to improve. Design
the weighting yourself and **tell us why** — we're far more interested in your
reasoning and its failure modes than in a specific formula.

**3. Surface it — a dashboard.**
Show the person how they're doing in a way that actually means something to them. A
raw number doesn't: "you used your phone for 3 hours" — so what? Is that a lot? Better
than usual? Give it meaning by comparing it to the person's own past, showing whether
things are going up or down over the month, and adding a little context — e.g. "30
minutes less than your usual, and your longest break was Saturday afternoon." Keep the
tone warm and honest: encouraging, never shaming. A few charts of how things trend
over the month are expected.

**4. Intelligence — at least one alert and at least one action, built for real.**
The metrics tell a story over the month. Detect it.
- **Alert / anomaly (guardian-facing):** implement at least one rule that decides
  *this is worth surfacing to a guardian* — honoring the privacy line above. Think
  about what's genuinely worth interrupting someone for, versus noise.
- **Action / nudge (user-facing):** implement at least one on-device nudge that helps
  the user themselves (a block-screen message, a well-timed reminder, a suggestion).
  When would you show it, and when would you stay quiet?

You don't have to finish everything. A thoughtful, working slice of 1→4 beats a broad
sketch of all of them.

---

## Format — your call

**Deliver it in whatever form best shows your thinking.** A small running app, a
notebook, a service with a simple UI, a well-argued write-up with figures — all fine.
Pick your own stack; use AI tools if that's how you work (we do). Two things we always
read:

- A short **README** with how to run it and, more importantly, the **decisions you
  made and why** — what you computed, what you deliberately left out, what you'd do
  next with more time.
- Your **reasoning about the two users** — what you found, and what you decided was
  (or wasn't) worth acting on.

## What we're looking at

- **Correctness** — do the metrics actually follow from the events?
- **Product judgment** — does what you built answer "so what?", and does it respect
  the privacy line?
- **Insight** — did you *find the story* in the data, not just plot it?
- **Engineering** — is the code clean, sensible, and something we'd want to build on?
- **Communication** — can you explain your choices and their trade-offs crisply?

## Notes

- Timestamps are **epoch milliseconds**; the device wall-clock is normalised to UTC,
  so `new Date(ts)` / `datetime.utcfromtimestamp(ts/1000)` gives you the local time.
  Day boundaries are at local midnight.
- The data is synthetic (no real users) and self-consistent, but not sanitised into
  tidiness — treat it like real device data.
- Questions are welcome. Knowing what to ask is part of the job.

Have fun with it.
