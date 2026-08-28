"""
Utilidades compartidas de los tests.

La mayoría de los tests construyen streams sintéticos a mano en vez de usar los
ficheros de datos: un test que depende del dato real sólo dice "hoy sale esto",
mientras que uno sintético dice "esta regla hace esto". Los ficheros reales se
usan sólo en `test_data_contract.py`, donde el objeto del test *es* el dato.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from balance.events import Timeline, load

DATA = Path(__file__).resolve().parents[1] / "data"

#: Día base de los streams sintéticos. Cualquiera vale; se fija uno para que los
#: tests sean deterministas y las fechas se puedan escribir a mano.
DAY0 = dt.date(2026, 5, 1)


def ts(day_offset: int, clock: str) -> int:
    """`ts(0, "23:50")` → epoch millis de ese instante en el día base.

    El reloj del dispositivo viene normalizado a UTC (ver SCHEMA.md), así que
    aquí se construye igual: sin zona horaria local de por medio.
    """
    h, m, *rest = (int(x) for x in clock.split(":"))
    sec = rest[0] if rest else 0
    moment = dt.datetime.combine(
        DAY0 + dt.timedelta(days=day_offset),
        dt.time(h, m, sec), tzinfo=dt.timezone.utc)
    return int(moment.timestamp() * 1000)


def ev(kind: str, day_offset: int, clock: str, **extra) -> dict:
    """Un evento con los ocho campos del schema, los que no apliquen a None."""
    base = {
        "id": 0, "event_type": kind, "timestamp_millis": ts(day_offset, clock),
        "package_name": None, "url_domain": None, "category": None,
        "block_type": None, "is_keyguard_locked": None,
    }
    base.update(extra)
    return base


def build(events: list[dict], user: str = "T", tmp_path: Path | None = None) -> Timeline:
    """Construye un `Timeline` desde una lista de eventos en memoria.

    Escribe un JSON temporal en vez de llamar a las funciones internas, para que
    el test recorra exactamente el mismo camino que producción (`load`).
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
