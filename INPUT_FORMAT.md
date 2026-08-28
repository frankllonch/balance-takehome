# Input format

The pipeline reads one JSON file per profile: a flat array of behavioural
events, sorted ascending by time, one object per event. This document describes
the format in the terms this codebase uses; it is a restatement written for
maintainers, not the upstream specification.

## Event object

Every object carries the same eight fields. Fields that do not apply to an
event type are `null`.

| Field | Type | Meaning |
|---|---|---|
| `id` | int | Monotonic within the file, in time order. Used only to break ties when sorting. |
| `event_type` | str | One of the six types below. |
| `timestamp_millis` | int | Epoch milliseconds. The device wall clock is normalised to UTC, so reading it as UTC gives local time. Day boundaries fall at local midnight. |
| `package_name` | str \| null | Android package. Set on `APP_FOREGROUND`, and on `BLOCK` when an app was blocked. |
| `url_domain` | str \| null | Domain only, never a path or a query string. Set on `URL_VISIT`, and on `BLOCK` when a site was blocked. |
| `category` | str \| null | Content category. Set on `APP_FOREGROUND`, `URL_VISIT` and `BLOCK`. |
| `block_type` | str \| null | Only on `BLOCK`: `APP`, `URL` or `NUDITY` (on-device nudity detection). |
| `is_keyguard_locked` | bool \| null | Lock state when a screen event fired. `true` on a `SCREEN_ON` where the phone was not unlocked; `false` on `USER_PRESENT`. |

## Event types

| Type | Fires when |
|---|---|
| `SCREEN_ON` | The screen lights up. May be a passive glance or the start of real use. |
| `USER_PRESENT` | The user actually unlocks the phone. |
| `SCREEN_OFF` | The screen goes dark. |
| `APP_FOREGROUND` | An app comes to the foreground. |
| `URL_VISIT` | A page is visited in the browser. |
| `BLOCK` | An app or site was stopped. The content did **not** open. |

## Categories

```
ADULT · GAMBLING · SOCIAL_MEDIA · MESSAGING · GAMING
ENTERTAINMENT · NEWS · SHOPPING · OTHER
```

`ADULT` and `GAMBLING` are treated as sensitive throughout the codebase
(`SENSITIVE` in `balance/events.py`); they are the only ones that can justify
notifying a guardian. The rest are ordinary distraction.

## What the stream does and does not contain

- A `BLOCK` means an attempt was stopped. A `URL_VISIT` or an `APP_FOREGROUND`
  means content actually was shown.
- Sessions are implicit: they are reconstructed from `SCREEN_ON` … `SCREEN_OFF`.
  See `balance/events.py` for why that reconstruction is not a simple pairing.
- Time per app or per site is not given. It is derived from event ordering: an
  app is in front from its `APP_FOREGROUND` until the next foreground change,
  block, screen-on or screen-off.

## Where the data lives

`data/*.json`, one file per profile, wired in `PROFILES` in `balance/run.py`
and `DATA` in `app.py`.
