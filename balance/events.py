"""
Capa 0 · eventos crudos → estructuras limpias.

Todo lo que sabemos del stream vive aquí. El resto del código no vuelve a
tocar un evento suelto: consume `Timeline`.

Decisiones no obvias (documentadas porque el dato NO viene limpio):

1. **`SCREEN_ON` / `SCREEN_OFF` se solapan.** En `user_a` hay 77 `SCREEN_ON`
   con la pantalla ya encendida, y 411 en `user_b`, compensados más tarde por
   `SCREEN_OFF` consecutivos. Sólo hay una pantalla, así que la pregunta es qué
   OFF cierra qué ON, y el dato no lo dice.

   La respuesta es que **da igual**: sea cual sea el emparejamiento, la unión de
   los tramos es la misma, y "la pantalla estuvo encendida" es exactamente esa
   unión. Se modela con un **contador de profundidad** (ON suma, OFF resta;
   encendida mientras depth > 0), que devuelve esa unión sin tener que elegir
   emparejamiento.

   Elegir uno sí cambia el resultado, y en las dos direcciones. Sobre `user_a`:

   | Estrategia | Horas | Frente a la unión |
   |---|---|---|
   | Unión (contador de profundidad) | 61,1 | — |
   | Pila LIFO | 64,9 | +6 % · cuenta dos veces el solape |
   | Cola FIFO | 56,7 | −7 % · pierde el tramo sobrante |
   | Reiniciar el reloj en cada ON | 53,0 | −13 % |

   Sobre `user_b`, donde hay 411 solapes, el abanico va de 93,4 h a 155,1 h
   frente a 131,1 de la unión.

2. Un `SCREEN_ON` es un **vistazo** (glance) salvo que aparezca un
   `USER_PRESENT` antes del siguiente ON/OFF: eso es un **pickup real**.
   En `user_a`: 573 pickups y 133 vistazos sobre 706 `SCREEN_ON`.
   En `user_b`: 1.349 y 131 sobre 1.480.

3. Los eventos de app, URL o bloqueo con la pantalla apagada **no generan
   tiempo de uso**. En estos dos ficheros el caso no llega a darse ni una vez;
   la guarda está porque un dispositivo real sí emite eventos con la pantalla
   apagada (música de fondo, sincronizaciones, bloqueos de red) y sin ella una
   app se comería el día entero.

4. Los tramos de pantalla que cruzan medianoche se parten en el corte de día
   local, para que "screen time del día" sume exactamente el día.

5. Anomalías que sí aparecen: 4 `USER_PRESENT` duplicados dentro de un mismo
   tramo en `user_a` y 6 en `user_b`. Se registran en `Timeline.anomalies` y no
   se descartan en silencio.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Vocabulario del schema
# ---------------------------------------------------------------------------

SCREEN_ON = "SCREEN_ON"
SCREEN_OFF = "SCREEN_OFF"
USER_PRESENT = "USER_PRESENT"
APP_FOREGROUND = "APP_FOREGROUND"
URL_VISIT = "URL_VISIT"
BLOCK = "BLOCK"

CATEGORIES = [
    "ADULT", "GAMBLING", "SOCIAL_MEDIA", "MESSAGING", "GAMING",
    "ENTERTAINMENT", "NEWS", "SHOPPING", "OTHER",
]

#: Categorías "sensibles" según SCHEMA.md: las únicas que justifican avisar
#: a un tutor. El resto son distracción ordinaria.
SENSITIVE = {"ADULT", "GAMBLING"}

#: Categorías que consideramos "distracción" a efectos de score.
DISTRACTING = {"SOCIAL_MEDIA", "ENTERTAINMENT", "GAMING"}

#: Nombre legible por paquete. Sólo cosmético (nunca sale del dispositivo).
APP_LABELS = {
    "com.whatsapp": "WhatsApp",
    "com.android.chrome": "Chrome",
    "com.spotify.music": "Spotify",
    "com.google.android.gm": "Gmail",
    "com.google.android.apps.maps": "Maps",
    "com.google.android.dialer": "Teléfono",
    "com.google.android.calendar": "Calendario",
    "com.google.android.youtube": "YouTube",
    "com.netflix.mediaclient": "Netflix",
    "com.facebook.katana": "Facebook",
    "com.twitter.android": "X / Twitter",
    "com.instagram.android": "Instagram",
    "com.zhiliaoapp.musically": "TikTok",
    "com.snapchat.android": "Snapchat",
    "com.google.android.apps.messaging": "Mensajes",
    "org.telegram.messenger": "Telegram",
    "com.amazon.kindle": "Kindle",
    "com.roblox.client": "Roblox",
    "com.supercell.clashofclans": "Clash of Clans",
    "com.duolingo": "Duolingo",
    "com.google.android.keep": "Keep",
    "com.microsoft.office.outlook": "Outlook",
    "com.reddit.frontpage": "Reddit",
}


def app_label(package: str) -> str:
    return APP_LABELS.get(package, package.split(".")[-1].title())


# ---------------------------------------------------------------------------
# Tiempo
# ---------------------------------------------------------------------------

def to_dt(ms: int) -> datetime:
    """epoch millis → hora local de pared (el reloj ya viene normalizado a UTC)."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def day_of(ms: int) -> date:
    return to_dt(ms).date()


def midnight_ms(d: date) -> int:
    return int(datetime.combine(d, time.min).replace(tzinfo=timezone.utc).timestamp() * 1000)


# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------

@dataclass
class Interval:
    """Un tramo de pantalla encendida, ya recortado a un único día."""
    start_ms: int
    end_ms: int
    day: date
    pickups: int = 0          # unlocks reales dentro del tramo
    glances: int = 0          # SCREEN_ON sin unlock dentro del tramo

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000

    @property
    def is_pickup(self) -> bool:
        return self.pickups > 0


@dataclass
class Usage:
    """Un trozo de tiempo atribuido a una app o a un dominio."""
    start_ms: int
    end_ms: int
    day: date
    kind: str                 # 'app' | 'site'
    key: str                  # package_name | url_domain
    category: str

    @property
    def seconds(self) -> float:
        return (self.end_ms - self.start_ms) / 1000


@dataclass
class Block:
    ts_ms: int
    day: date
    block_type: str           # APP | URL | NUDITY
    category: str
    target: str               # package o dominio


@dataclass
class Timeline:
    """Todo lo derivado del stream de un usuario, ya limpio."""
    user: str
    events: list[dict]
    intervals: list[Interval]
    usages: list[Usage]
    blocks: list[Block]
    days: list[date]
    anomalies: Counter = field(default_factory=Counter)

    # -- helpers de filtrado -------------------------------------------------
    def intervals_on(self, d: date) -> list[Interval]:
        return [i for i in self.intervals if i.day == d]

    def usages_on(self, d: date) -> list[Usage]:
        return [u for u in self.usages if u.day == d]

    def blocks_on(self, d: date) -> list[Block]:
        return [b for b in self.blocks if b.day == d]


# ---------------------------------------------------------------------------
# Reconstrucción
# ---------------------------------------------------------------------------

#: Si una app queda "en primer plano" más de esto sin ningún evento que la
#: cierre, asumimos que se perdió el `SCREEN_OFF` y se corta. El tope está por
#: encima del tramo de pantalla más largo observado (21,9 min en `user_a`,
#: 32,6 min en `user_b`), así que hoy no recorta nada real: es una red de
#: seguridad, no una regla de negocio.
MAX_FOREGROUND_S = 45 * 60


def _screen_intervals(events: list[dict], anomalies: Counter) -> list[Interval]:
    """Unión de tramos de pantalla encendida, partidos por medianoche.

    Contador de profundidad: ON suma, OFF resta. La pantalla está encendida
    mientras depth > 0. Los pickups/glances se atribuyen al tramo abierto.
    """
    raw: list[Interval] = []
    depth = 0
    start = None
    pickups = glances = 0
    pending_on = False           # hay un SCREEN_ON esperando veredicto

    for e in events:
        t = e["event_type"]
        ts = e["timestamp_millis"]

        if t == SCREEN_ON:
            if pending_on:       # el ON anterior murió sin unlock → vistazo
                glances += 1
            pending_on = True
            if depth == 0:
                start = ts
                pickups = glances = 0
            depth += 1

        elif t == USER_PRESENT:
            if depth == 0:
                # Unlock sin SCREEN_ON previo. No ocurre en los dos ficheros de
                # ejemplo, pero es físicamente posible si se pierde el ON.
                anomalies["USER_PRESENT sin SCREEN_ON"] += 1
                depth, start, pickups, glances = 1, ts, 0, 0
            if pending_on:
                pickups += 1
                pending_on = False
            else:
                anomalies["USER_PRESENT duplicado en tramo"] += 1

        elif t == SCREEN_OFF:
            if depth == 0:
                anomalies["SCREEN_OFF con pantalla apagada"] += 1
                continue
            if pending_on:
                glances += 1
                pending_on = False
            depth -= 1
            if depth == 0:
                raw.append(Interval(start, ts, day_of(start), pickups, glances))

    if depth > 0:                # el fichero se corta con la pantalla encendida
        anomalies["tramo abierto al final del fichero"] += 1
        last = events[-1]["timestamp_millis"]
        raw.append(Interval(start, last, day_of(start), pickups, glances))

    return _split_midnight(raw)


def _split_midnight(intervals: list[Interval]) -> list[Interval]:
    """Parte cualquier tramo que cruce medianoche. Los pickups van al día en
    que se produjo el unlock, es decir, al primer trozo."""
    out: list[Interval] = []
    for iv in intervals:
        cur = iv
        while True:
            next_midnight = midnight_ms(cur.day + timedelta(days=1))
            if cur.end_ms <= next_midnight:
                out.append(cur)
                break
            out.append(Interval(cur.start_ms, next_midnight, cur.day,
                                cur.pickups, cur.glances))
            cur = Interval(next_midnight, cur.end_ms,
                           day_of(next_midnight), 0, 0)
    return out


def _screen_on_lookup(intervals: list[Interval]):
    """Devuelve (fn_esta_encendida, fn_fin_del_tramo) con búsqueda binaria."""
    starts = [iv.start_ms for iv in intervals]

    def enclosing(ts: int) -> Interval | None:
        i = bisect_left(starts, ts + 1) - 1
        if i < 0:
            return None
        iv = intervals[i]
        return iv if iv.start_ms <= ts <= iv.end_ms else None

    return enclosing


def _usages(events: list[dict], intervals: list[Interval],
            anomalies: Counter) -> list[Usage]:
    """Atribuye tiempo a apps y a dominios a partir del orden de los eventos.

    Una app está "delante" desde su `APP_FOREGROUND` hasta el siguiente cambio
    de foreground, un `BLOCK`, un `SCREEN_ON` o el apagado de pantalla. Un
    `URL_VISIT` ocupa el navegador: su tiempo se descuenta de la app y se
    atribuye al dominio, porque Chrome es un contenedor y no un destino.

    Un `SCREEN_ON` cierra el foreground aunque la pantalla siga encendida (caso
    del solape): el usuario ha vuelto a la pantalla de bloqueo, y atribuirle ese
    rato a la app anterior sería inventarlo. El coste es que parte del tiempo
    queda sin atribuir, y por eso la cobertura no llega al 100 %: 86 % en
    `user_a`, 67 % en `user_b`.
    """
    enclosing = _screen_on_lookup(intervals)
    out: list[Usage] = []

    # eventos que "cierran" el foreground actual
    closers = {APP_FOREGROUND, URL_VISIT, BLOCK, SCREEN_OFF, SCREEN_ON}
    open_ev: dict | None = None   # {'kind','key','category','ts'}

    def close(at_ms: int):
        nonlocal open_ev
        if open_ev is None:
            return
        end = min(at_ms, open_ev["limit"])
        if end > open_ev["ts"]:
            out.append(Usage(open_ev["ts"], end, day_of(open_ev["ts"]),
                             open_ev["kind"], open_ev["key"], open_ev["category"]))
        open_ev = None

    for e in events:
        t = e["event_type"]
        ts = e["timestamp_millis"]

        if t in closers:
            close(ts)

        if t in (APP_FOREGROUND, URL_VISIT):
            iv = enclosing(ts)
            if iv is None:
                # ocurre con la pantalla apagada: música de fondo, sync.
                anomalies[f"{t} con pantalla apagada"] += 1
                continue
            open_ev = {
                "kind": "app" if t == APP_FOREGROUND else "site",
                "key": e["package_name"] if t == APP_FOREGROUND else e["url_domain"],
                "category": e["category"] or "OTHER",
                "ts": ts,
                "limit": min(iv.end_ms, ts + MAX_FOREGROUND_S * 1000),
            }

    close(events[-1]["timestamp_millis"])
    return [u for u in out if u.seconds > 0]


def _blocks(events: list[dict]) -> list[Block]:
    return [
        Block(e["timestamp_millis"], day_of(e["timestamp_millis"]),
              e["block_type"] or "APP", e["category"] or "OTHER",
              e["package_name"] or e["url_domain"] or "desconocido")
        for e in events if e["event_type"] == BLOCK
    ]


def load(path: str | Path, user: str) -> Timeline:
    events = json.loads(Path(path).read_text())
    events.sort(key=lambda e: (e["timestamp_millis"], e["id"]))

    anomalies: Counter = Counter()
    intervals = _screen_intervals(events, anomalies)
    usages = _usages(events, intervals, anomalies)
    blocks = _blocks(events)

    first, last = day_of(events[0]["timestamp_millis"]), day_of(events[-1]["timestamp_millis"])
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]

    return Timeline(user, events, intervals, usages, blocks, days, anomalies)
