"""
Capa 1 · Timeline → métricas diarias y semanales.

Una fila por día y usuario. Todo lo que el dashboard dibuja sale de aquí.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from statistics import median

import pandas as pd

from .events import (
    DISTRACTING, SENSITIVE, Interval, Timeline, app_label, midnight_ms, to_dt,
)

#: Ventana de vigilia. Fuera de ella el "tiempo offline" no es mérito: estás
#: durmiendo. Se usa para normalizar offline y racha más larga sin pantalla.
WAKE_START, WAKE_END = 7, 23        # 07:00 – 23:00 hora local

#: Franja nocturna protegida: uso aquí es el que más cuesta al descanso.
NIGHT_START, NIGHT_END = 23, 6      # 23:00 – 06:00


def _overlap_s(a0: int, a1: int, b0: int, b1: int) -> float:
    return max(0, min(a1, b1) - max(a0, b0)) / 1000


def _window_ms(d: date, h0: int, h1: int) -> tuple[int, int]:
    base = midnight_ms(d)
    return base + h0 * 3600_000, base + h1 * 3600_000


def _night_window(d: date) -> tuple[int, int]:
    """La **noche del día d**: 23:00 de d → 06:00 de d+1.

    El día natural sigue cortando a medianoche (lo pide el enunciado), pero el
    sueño no. Un mensaje a la 01:30 del martes pertenece a la noche del lunes,
    y así es como lo cuenta el usuario. Mantener las dos convenciones a la vez
    evita partir una misma noche en dos filas.
    """
    base = midnight_ms(d)
    return base + NIGHT_START * 3600_000, base + (24 + NIGHT_END) * 3600_000


def _shift_h(ms: int | None) -> float | None:
    """Hora del día en un eje que empieza a las 04:00, de forma que la
    madrugada (00:00–04:00) sale como 24–28 y no como 0–4. Sin esto, la media
    de 'hora de último uso' baja cuando alguien se acuesta *más tarde*."""
    if not ms:
        return None
    t = to_dt(ms)
    h = t.hour + t.minute / 60
    return h + 24 if h < 4 else h


def _fmt_clock(ms: int | None) -> str | None:
    return to_dt(ms).strftime("%H:%M") if ms else None


#: Nombre del día y franja horaria, para poder decir "el sábado por la tarde"
#: en vez de sólo "3 h 47 min". La duración sin el cuándo no sitúa nada.
DIAS_ES = ["el lunes", "el martes", "el miércoles", "el jueves",
           "el viernes", "el sábado", "el domingo"]
FRANJAS = [(6, "por la mañana"), (12, "al mediodía"), (15, "por la tarde"),
           (20, "por la noche"), (24, "de madrugada")]


def _franja(ms: int) -> str:
    """`ms` → "el sábado por la tarde"."""
    t = to_dt(ms)
    tramo = next(nombre for limite, nombre in FRANJAS if t.hour < limite)
    return f"{DIAS_ES[t.weekday()]} {tramo}"


def _longest_gap(intervals: list[Interval], w0: int,
                 w1: int) -> tuple[float, int | None]:
    """Racha más larga sin pantalla dentro de la vigilia, y cuándo empieza.

    Devuelve el inicio además de la duración porque una racha sin momento no
    dice nada: "3 h 47 min" es un número, "3 h 47 min el sábado por la tarde"
    es algo que la persona reconoce.
    """
    pts = sorted((max(i.start_ms, w0), min(i.end_ms, w1))
                 for i in intervals if i.end_ms > w0 and i.start_ms < w1)
    best, best_start, cursor = 0.0, w0, w0
    for s, e in pts:
        if (s - cursor) / 1000 > best:
            best, best_start = (s - cursor) / 1000, cursor
        cursor = max(cursor, e)
    if (w1 - cursor) / 1000 > best:
        best, best_start = (w1 - cursor) / 1000, cursor
    return best, (best_start if best > 0 else None)


def daily_frame(tl: Timeline) -> pd.DataFrame:
    """Una fila por día con todas las métricas base."""
    by_day_iv: dict[date, list[Interval]] = defaultdict(list)
    for iv in tl.intervals:
        by_day_iv[iv.day].append(iv)

    by_day_use = defaultdict(list)
    for u in tl.usages:
        by_day_use[u.day].append(u)

    by_day_block = defaultdict(list)
    for b in tl.blocks:
        by_day_block[b.day].append(b)

    # Cambios de app: transición real de foreground entre paquetes distintos.
    # El contador se reinicia en cada día. Sin eso, la primera app de la mañana
    # cuenta como cambio respecto a la última de la noche anterior, lo que
    # sumaba un cambio falso por día (~5 % del total) y, peor, hacía que un
    # "cambio" abarcase ocho horas de sueño.
    switches_by_day: Counter = Counter()
    last_key_by_day: dict[date, str] = {}
    for u in sorted(tl.usages, key=lambda x: x.start_ms):
        if u.kind != "app":
            continue
        prev = last_key_by_day.get(u.day)
        if prev is not None and u.key != prev:
            switches_by_day[u.day] += 1
        last_key_by_day[u.day] = u.key

    file_start = tl.events[0]["timestamp_millis"]
    file_end = tl.events[-1]["timestamp_millis"]

    rows = []
    for d in tl.days:
        ivs = sorted(by_day_iv[d], key=lambda i: i.start_ms)
        uses = by_day_use[d]
        blocks = by_day_block[d]

        screen_s = sum(i.seconds for i in ivs)
        pickups = sum(i.pickups for i in ivs)
        glances = sum(i.glances for i in ivs)

        w0, w1 = _window_ms(d, WAKE_START, WAKE_END)
        screen_wake_s = sum(_overlap_s(i.start_ms, i.end_ms, w0, w1) for i in ivs)

        # la noche se mide sobre TODOS los tramos, no sólo los de este día:
        # la noche del día d se extiende hasta las 06:00 del día siguiente.
        n0, n1 = _night_window(d)
        night_s = sum(_overlap_s(i.start_ms, i.end_ms, n0, n1) for i in tl.intervals)
        night_pickups = sum(i.pickups for i in tl.intervals if n0 <= i.start_ms < n1)
        night_last = max((i.end_ms for i in tl.intervals
                          if i.start_ms < n1 and i.end_ms > n0), default=None)

        # "Primer pickup" = el primero a partir de las 06:00. Sin ese corte, un
        # día que arranca a las 00:20 (cola de la noche anterior) se registraría
        # como "empezó a las 00:20", que no es empezar el día: es no haberlo
        # terminado. Ese fenómeno se mide aparte, en `night_*`.
        offline_s, offline_start = _longest_gap(ivs, w0, w1)

        morning = midnight_ms(d) + NIGHT_END * 3600_000
        real = [i for i in ivs if i.is_pickup and i.start_ms >= morning]
        first_pick = min((i.start_ms for i in real), default=None)
        last_use = max((i.end_ms for i in ivs), default=None)

        cat_s: Counter = Counter()
        app_s: Counter = Counter()
        site_s: Counter = Counter()
        for u in uses:
            cat_s[u.category] += u.seconds
            (app_s if u.kind == "app" else site_s)[u.key] += u.seconds
        attributed = sum(cat_s.values())
        distract_s = sum(v for k, v in cat_s.items() if k in DISTRACTING)

        bt = Counter(b.block_type for b in blocks)
        bc = Counter(b.category for b in blocks)

        # cuánto del día natural cubre realmente el fichero. El último día de
        # user_b sólo llega hasta las 00:46; promediarlo hundiría las medias.
        d0, d1 = midnight_ms(d), midnight_ms(d + timedelta(days=1))
        coverage_h = max(0, min(file_end, d1) - max(file_start, d0)) / 3600_000

        rows.append({
            "day": d,
            "dow": d.weekday(),
            "is_weekend": d.weekday() >= 5,
            "week": (d - tl.days[0]).days // 7 + 1,
            "coverage_h": coverage_h,
            "is_partial": coverage_h < 12,

            "screen_s": screen_s,
            "screen_min": screen_s / 60,
            "screen_wake_s": screen_wake_s,
            "offline_wake_s": max(0.0, (w1 - w0) / 1000 - screen_wake_s),
            "offline_wake_h": max(0.0, (w1 - w0) / 1000 - screen_wake_s) / 3600,
            "sessions": len(ivs),
            "longest_session_s": max((i.seconds for i in ivs), default=0),
            # mediana de verdad: con n par, la media de los dos centrales
            "median_session_s": (median(i.seconds for i in ivs) if ivs else 0),

            "pickups": pickups,
            "glances": glances,
            "pickup_rate": pickups / max(1, pickups + glances),
            "pickups_per_wake_hour": pickups / (WAKE_END - WAKE_START),

            "first_pickup_ms": first_pick,
            "first_pickup_h": _shift_h(first_pick),
            "last_use_ms": last_use,
            "last_use_h": _shift_h(last_use),
            "night_s": night_s,
            "night_min": night_s / 60,
            "night_pickups": night_pickups,
            "night_end_h": _shift_h(night_last),
            "longest_offline_s": offline_s,
            "longest_offline_h": offline_s / 3600,
            "longest_offline_start_ms": offline_start,
            "longest_offline_when": (_franja(offline_start)
                                     if offline_start else None),

            "distinct_apps": len({u.key for u in uses if u.kind == "app"}),
            "distinct_sites": len({u.key for u in uses if u.kind == "site"}),
            "app_switches": switches_by_day[d],
            "switches_per_screen_hour": (switches_by_day[d] / (screen_s / 3600)
                                         if screen_s > 60 else 0),

            "attributed_s": attributed,
            "distract_s": distract_s,
            "distract_share": distract_s / attributed if attributed else 0,

            "blocks": len(blocks),
            "blocks_app": bt.get("APP", 0),
            "blocks_url": bt.get("URL", 0),
            "blocks_nudity": bt.get("NUDITY", 0),
            "blocks_sensitive": sum(v for k, v in bc.items() if k in SENSITIVE),
            "blocks_adult": bc.get("ADULT", 0),
            "blocks_gambling": bc.get("GAMBLING", 0),
            "blocks_social": bc.get("SOCIAL_MEDIA", 0),
            "blocks_gaming": bc.get("GAMING", 0),
            "blocks_entertainment": bc.get("ENTERTAINMENT", 0),

            "_cat_s": dict(cat_s),
            "_app_s": dict(app_s),
            "_site_s": dict(site_s),
        })

    df = pd.DataFrame(rows).set_index("day", drop=False)
    df = df[~df["is_partial"]].copy()      # fuera los días truncados por el fichero
    df["first_pickup_clock"] = [_fmt_clock(m) for m in df["first_pickup_ms"]]
    df["last_use_clock"] = [_fmt_clock(m) for m in df["last_use_ms"]]

    # baseline personal: mediana móvil de los 14 días anteriores (sin el de hoy).
    # Mediana y no media: un festivo raro no debe mover "lo normal en mí".
    for col in ("screen_min", "pickups", "night_min", "blocks"):
        df[f"{col}_baseline"] = df[col].shift(1).rolling(14, min_periods=5).median()
        df[f"{col}_delta"] = df[col] - df[f"{col}_baseline"]
    return df


# ---------------------------------------------------------------------------
# Agregados no diarios
# ---------------------------------------------------------------------------

def totals(tl: Timeline, df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Ranking de apps o dominios por tiempo total y aperturas.

    `df` fija qué días cuentan: los truncados por el borde del fichero ya se
    han caído de él, y aquí tienen que caerse igual para que los totales
    cuadren con los KPI.
    """
    days = set(df["day"])
    secs: Counter = Counter()
    opens: Counter = Counter()
    cats: dict[str, str] = {}
    for u in tl.usages:
        if u.kind != kind or u.day not in days:
            continue
        secs[u.key] += u.seconds
        opens[u.key] += 1
        cats[u.key] = u.category
    out = pd.DataFrame({
        "key": list(secs),
        "label": [app_label(k) if kind == "app" else k for k in secs],
        "category": [cats[k] for k in secs],
        "minutes": [secs[k] / 60 for k in secs],
        "opens": [opens[k] for k in secs],
    })
    if out.empty:
        return out
    out["min_per_open"] = out.minutes / out.opens
    return out.sort_values("minutes", ascending=False).reset_index(drop=True)


def category_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Minutos por categoría y día (formato largo, listo para plotly)."""
    rows = []
    for d, cats in zip(df["day"], df["_cat_s"]):
        for c, s in cats.items():
            rows.append({"day": d, "category": c, "minutes": s / 60})
    return pd.DataFrame(rows)


def hourly_heat(tl: Timeline, days: set[date] | None = None) -> pd.DataFrame:
    """Minutos de pantalla por (día de la semana, hora): reloj de uso."""
    grid: Counter = Counter()
    for iv in tl.intervals:
        if days is not None and iv.day not in days:
            continue
        start = iv.start_ms
        while start < iv.end_ms:
            dtm = to_dt(start)
            hour_end = midnight_ms(dtm.date()) + (dtm.hour + 1) * 3600_000
            end = min(iv.end_ms, hour_end)
            grid[(dtm.weekday(), dtm.hour)] += (end - start) / 60_000
            start = end
    return pd.DataFrame(
        [{"dow": k[0], "hour": k[1], "minutes": v} for k, v in grid.items()]
    )


def blocks_frame(tl: Timeline, days: set[date] | None = None) -> pd.DataFrame:
    return pd.DataFrame([{
        "day": b.day, "hour": to_dt(b.ts_ms).hour,
        "block_type": b.block_type, "category": b.category, "target": b.target,
    } for b in tl.blocks if days is None or b.day in days])


def weekly_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por semana, con la variación respecto a la semana anterior.

    Las mismas magnitudes que el frame diario pero promediadas por día, para
    que una semana corta (la última del periodo suele serlo) no parezca mejor
    sólo por tener menos días. `is_partial` marca las que no llegan a 7.
    """
    w = df.groupby("week").agg(
        days=("day", "count"),
        start=("day", "min"), end=("day", "max"),
        screen_min=("screen_min", "mean"),
        pickups=("pickups", "mean"),
        glances=("glances", "mean"),
        night_min=("night_min", "mean"),
        night_pickups=("night_pickups", "mean"),
        night_end_h=("night_end_h", "median"),
        first_pickup_h=("first_pickup_h", "median"),
        longest_offline_h=("longest_offline_s", lambda s: s.mean() / 3600),
        best_offline_h=("longest_offline_h", "max"),
        distinct_apps=("distinct_apps", "mean"),
        switches_per_screen_hour=("switches_per_screen_hour", "mean"),
        distract_share=("distract_share", "mean"),
        blocks=("blocks", "mean"),
        blocks_total=("blocks", "sum"),
        blocks_sensitive=("blocks_sensitive", "sum"),
        score=("score", "mean"),
    )
    # El "cuándo" de la mejor racha de cada semana: es la frase que convierte
    # una duración en algo que la persona reconoce.
    mejor = df.loc[df.groupby("week")["longest_offline_s"].idxmax()]
    w["best_offline_when"] = mejor.set_index("week")["longest_offline_when"]
    w["best_offline_day"] = mejor.set_index("week")["day"]

    w["is_partial"] = w["days"] < 7
    for col in ("screen_min", "pickups", "night_min", "blocks", "score",
                "distract_share", "longest_offline_h", "night_end_h"):
        w[f"{col}_prev"] = w[col].shift(1)
        w[f"{col}_delta"] = w[col] - w[f"{col}_prev"]
    return w
