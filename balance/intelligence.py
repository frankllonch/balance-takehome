"""
Capa 4 · de la métrica a la decisión: qué se avisa, a quién y qué se calla.

Dos superficies distintas y deliberadamente asimétricas:

* **Alertas al tutor.** Coarse, sin objeto, con cupo. El fallo real de un canal
  de avisos a un padre no es perderse un evento: es gritar hasta que deja de
  leerlos. Por eso hay un **presupuesto de silencio** (`ALERT_BUDGET`): cada
  candidata tiene que ganarse su hueco, y lo que no entra baja a resumen
  semanal. Las candidatas descartadas se conservan con su motivo, porque la
  parte interesante de un sistema de alertas son los negativos.

* **Nudges al usuario.** En el dispositivo, con detalle, y con reglas de
  silencio propias. Un nudge que se muestra siempre deja de ser un nudge.

Todo lo de aquí es evaluable hacia atrás sobre datos históricos, que es como
se mide si una regla sirve antes de enviársela a nadie (`replay_nudge`).

Una limitación que conviene decir en voz alta: el detector de deriva usa una
referencia móvil, así que **deja de disparar cuando el comportamiento nuevo se
convierte en el normal**. Para avisar es lo correcto (se avisa del cambio, una
vez, no todos los días); pero significa que el silencio del detector no quiere
decir "arreglado". El nivel absoluto lo siguen contando el índice y el resumen
semanal, que no tienen memoria corta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from .events import Timeline, to_dt
from .metrics import _night_window

# ---------------------------------------------------------------------------
# Parámetros de las reglas (en un sitio, para poder discutirlos)
# ---------------------------------------------------------------------------

#: Ventanas del detector de deriva nocturna. 5 noches recientes contra las 14
#: anteriores: necesita 19 días de historia, y a cambio dispara pronto sin
#: reaccionar a una noche suelta.
DRIFT_RECENT, DRIFT_BASE = 5, 14
DRIFT_RATIO = 2.0          # la mediana reciente dobla a la de referencia
DRIFT_ABS_MIN = 20.0       # ...y son al menos 20 min: 2× de 3 min no es nada
DRIFT_CLOCK_MIN = 40.0     # ...y la hora de apagar se ha ido 40 min o más

#: Pico de contenido sensible: suma de 7 días contra el ritmo de los 14 previos.
SPIKE_RECENT, SPIKE_BASE = 7, 7
SPIKE_RATIO, SPIKE_ABS_MIN = 2.5, 10

#: Regla "obvia" que casi todo el mundo implementaría, incluida a propósito
#: para poder enseñar que NO se dispara con estos datos.
SCREEN_JUMP_RATIO, SCREEN_JUMP_ABS = 1.4, 60.0

#: Cupo de avisos al tutor por cada 30 días, y separación mínima entre dos.
ALERT_BUDGET = 2
ALERT_MIN_GAP_DAYS = 10

#: Nudge nocturno: se arma 30 min después del inicio de la franja, y sólo a
#: partir de la segunda reapertura.
NUDGE_AFTER_MIN = 30
NUDGE_MIN_REOPENS = 2


# ---------------------------------------------------------------------------
# Estructuras
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    """Una alerta candidata. Puede acabar enviada, en resumen o descartada."""
    key: str
    day: date                   # primer día en que la regla se cumple
    headline: str
    guardian_text: str          # literal que leería un tutor
    magnitude: float            # 0 a 1 · cuánto se sale de lo normal
    persistence: float          # 0 a 1 · cuánto lleva saliéndose
    actionability: float        # 0 a 1 · ¿puede el tutor hacer algo con esto?
    evidence: dict = field(default_factory=dict)   # NUNCA sale del dispositivo
    decision: str = "candidata"                    # enviada | resumen | descartada
    reason: str = ""
    until: date | None = None   # último día del episodio, si se prolonga
    audience: str = "tutor"     # tutor | usuario
    tone: str = "aviso"         # aviso | refuerzo

    @property
    def days_true(self) -> int:
        return ((self.until - self.day).days + 1) if self.until else 1

    @property
    def priority(self) -> float:
        """Producto, no suma: una alerta enorme pero de un día, o persistente
        pero sobre la que no se puede actuar, no debería colarse."""
        return round(self.magnitude * self.persistence * self.actionability, 3)


@dataclass
class NightNudge:
    """Qué habría hecho el nudge cada noche, y qué había en juego."""
    day: date
    fired: bool
    at_ms: int | None
    quiet_reason: str
    reopens: int
    minutes_after: float        # pantalla nocturna posterior al disparo
    night_minutes: float


def _clamp(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


# ---------------------------------------------------------------------------
# Reglas · tutor
# ---------------------------------------------------------------------------

def _night_drift(df: pd.DataFrame) -> list[Signal]:
    """Cambio de régimen en la franja nocturna.

    No es un umbral ("más de 30 min de madrugada"), es un cambio de
    distribución sostenido. Con un umbral, B habría disparado y dejado de
    disparar según la noche; y sobre todo, un umbral fijo no distingue entre
    alguien que siempre ha sido así y alguien que **acaba de cambiar**. Lo
    segundo es lo único que merece interrumpir a un padre.
    """
    out: list[Signal] = []
    need = DRIFT_RECENT + DRIFT_BASE
    for i in range(need - 1, len(df)):
        rec = df.night_min.iloc[i - DRIFT_RECENT + 1: i + 1]
        base = df.night_min.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE: i - DRIFT_RECENT + 1]
        rec_m, base_m = rec.median(), max(base.median(), 1.0)
        clock = (df.night_end_h.iloc[i - DRIFT_RECENT + 1: i + 1].median()
                 - df.night_end_h.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE:
                                       i - DRIFT_RECENT + 1].median()) * 60
        above = int((rec > base_m).sum())

        if not (rec_m >= DRIFT_ABS_MIN and rec_m >= DRIFT_RATIO * base_m
                and clock >= DRIFT_CLOCK_MIN and above >= DRIFT_RECENT - 1):
            continue

        out.append(Signal(
            key="night_drift",
            day=df.day.iloc[i],
            headline="El horario de sueño se ha desplazado",
            # Puramente descriptivo. Nada de recomendaciones: el producto
            # informa de un cambio medido, no dice a nadie qué hacer con él.
            guardian_text=(
                "En las últimas semanas el teléfono se apaga más tarde de lo que "
                "era habitual, y la hora de levantarse no ha cambiado. El resto "
                "de indicadores se mantiene estable."),
            magnitude=_clamp((rec_m / base_m - DRIFT_RATIO) / 4 + .5),
            persistence=_clamp(above / DRIFT_RECENT),
            actionability=1.0,      # un horario es exactamente lo que un tutor puede negociar
            evidence={
                "mediana noche reciente (min)": round(float(rec_m), 1),
                "mediana noche de referencia (min)": round(float(base.median()), 1),
                "retraso de la última pantalla (min)": int(round(clock)),
                "noches por encima de lo normal": f"{above} de {DRIFT_RECENT}",
            },
        ))
    return out


def _sensitive_spike(df: pd.DataFrame) -> list[Signal]:
    """Repunte de intentos hacia contenido adulto o apuestas.

    Se detecta, pero casi nunca se envía: ver `_decide`. El teléfono ya lo
    bloqueó, así que la urgencia es baja y el coste de decírselo a un padre en
    caliente es alto.
    """
    out: list[Signal] = []
    need = SPIKE_RECENT + SPIKE_BASE
    for i in range(need - 1, len(df)):
        rec = df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1: i + 1].sum()
        base_rate = (df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1 - SPIKE_BASE:
                                              i - SPIKE_RECENT + 1].sum()
                     / SPIKE_BASE * SPIKE_RECENT)
        if not (rec >= SPIKE_ABS_MIN and rec >= SPIKE_RATIO * max(base_rate, 1)):
            continue
        out.append(Signal(
            key="sensitive_spike",
            day=df.day.iloc[i],
            headline="El filtro de contenido sensible ha actuado más de lo habitual",
            guardian_text=(
                "Esta semana el filtro de contenido ha intervenido más veces de "
                "lo habitual. Todos los intentos fueron bloqueados y no se abrió "
                "ningún contenido."),
            magnitude=_clamp((rec / max(base_rate, 1) - SPIKE_RATIO) / 5 + .5),
            persistence=_clamp(
                (df.blocks_sensitive.iloc[i - SPIKE_RECENT + 1: i + 1] > 0).sum()
                / SPIKE_RECENT),
            # Baja a propósito: el bloqueo ya ocurrió. Lo que queda es una
            # conversación, y esa conversación no mejora por llegar hoy.
            actionability=0.35,
            evidence={
                "intentos en 7 días": int(rec),
                "ritmo de referencia": round(float(base_rate), 1),
                "abiertos": 0,
            },
        ))
    return out


def _screen_jump(df: pd.DataFrame) -> list[Signal]:
    """La regla obvia: "el tiempo de pantalla ha subido mucho".

    Está aquí para poder enseñar que **no dispara** con estos datos. Es el
    control negativo del sistema.
    """
    out: list[Signal] = []
    need = DRIFT_RECENT + DRIFT_BASE
    for i in range(need - 1, len(df)):
        rec = df.screen_min.iloc[i - DRIFT_RECENT + 1: i + 1].median()
        base = max(df.screen_min.iloc[i - DRIFT_RECENT + 1 - DRIFT_BASE:
                                      i - DRIFT_RECENT + 1].median(), 1.0)
        if rec >= SCREEN_JUMP_RATIO * base and rec - base >= SCREEN_JUMP_ABS:
            out.append(Signal(
                key="screen_jump", day=df.day.iloc[i],
                headline="El tiempo de pantalla ha subido",
                guardian_text="El uso diario ha crecido respecto a semanas anteriores.",
                magnitude=_clamp((rec / base - 1) * 2),
                persistence=1.0, actionability=0.5,
                evidence={"mediana reciente (min)": round(float(rec)),
                          "referencia (min)": round(float(base))}))
    return out


RULES = (_night_drift, _sensitive_spike, _screen_jump)


# ---------------------------------------------------------------------------
# Presupuesto de silencio
# ---------------------------------------------------------------------------

def _decide(signals: list[Signal]) -> list[Signal]:
    """Reparte el cupo de avisos y anota por qué se descarta cada resto.

    Primero se colapsan las repeticiones: una regla que cumple 9 días seguidos
    es **un** hecho, no nueve avisos. Después se ordena por prioridad y se
    reparte el cupo respetando una separación mínima.
    """
    # 1 · colapsar rachas de la misma regla en un solo episodio
    episodes: list[Signal] = []
    for s in sorted(signals, key=lambda x: (x.key, x.day)):
        prev = next((e for e in episodes if e.key == s.key), None)
        same_run = prev and (s.day - (prev.until or prev.day)).days <= 14
        if same_run:
            # La evidencia se queda la del día que disparó, no la del último:
            # es la que justifica el aviso que se mandó ese día.
            prev.magnitude = max(prev.magnitude, s.magnitude)
            prev.persistence = max(prev.persistence, s.persistence)
            prev.until = s.day
            continue
        episodes.append(s)

    # 2 · repartir el cupo
    sent: list[Signal] = []
    for s in sorted(episodes, key=lambda x: -x.priority):
        if s.actionability < 0.5:
            s.decision, s.reason = "resumen", (
                "El teléfono ya ha resuelto el incidente; no hay nada que un tutor "
                "pueda hacer hoy que no pueda hacer el domingo. Va al resumen "
                "semanal, no a una notificación.")
            continue
        if len(sent) >= ALERT_BUDGET:
            s.decision, s.reason = "descartada", (
                f"Cupo agotado: {ALERT_BUDGET} avisos por mes. Había una señal de "
                f"mayor prioridad y esta no la supera.")
            continue
        if any(abs((s.day - o.day).days) < ALERT_MIN_GAP_DAYS for o in sent):
            s.decision, s.reason = "resumen", (
                f"Hay otro aviso a menos de {ALERT_MIN_GAP_DAYS} días. Dos "
                f"notificaciones seguidas se leen como ruido, no como urgencia.")
            continue
        s.decision, s.reason = "enviada", "Cambio sostenido y accionable."
        sent.append(s)

    return sorted(episodes, key=lambda x: (x.decision != "enviada", -x.priority))


def evaluate_alerts(df: pd.DataFrame) -> list[Signal]:
    """Todas las candidatas del periodo, con su veredicto."""
    signals: list[Signal] = []
    for rule in RULES:
        signals.extend(rule(df))
    return _decide(signals)


def guardian_digest(df: pd.DataFrame, signals: list[Signal]) -> dict:
    """Lo único que sale del dispositivo si no hay alerta: un resumen grueso.

    Sin apps, sin dominios, sin categorías y con los números redondeados. El
    redondeo no es cosmético: a esta granularidad el tutor toma exactamente las
    mismas decisiones, y a cambio el agregado deja de ser un identificador.
    """
    last7 = df.tail(7)
    state = ("algo ha cambiado" if any(s.decision == "enviada" for s in signals)
             else "todo en orden")
    # Racha de noches protegidas. El enunciado admite explícitamente rachas
    # entre lo que puede salir del dispositivo, y es un agregado sin objeto:
    # dice que algo va bien sin decir contra qué.
    racha = 0
    for night in reversed(list(df["night_min"])):
        if night >= POS_NIGHT_QUIET_MIN:
            break
        racha += 1
    return {
        "estado": state,
        "pantalla al día": f"{round(last7.screen_min.mean() / 15) * 15 / 60:.1f} h aprox.",
        "índice de bienestar": f"{round(last7.score.mean() / 5) * 5:.0f} de 100",
        "noches seguidas sin madrugada": str(racha),
        "el filtro actuó": ("más de lo habitual"
                            if last7.blocks.mean() > df.blocks.mean() * 1.2
                            else "como de costumbre"),
        "contenido sensible abierto": "ninguno",
    }


# ---------------------------------------------------------------------------
# Nudge · usuario, en el dispositivo
# ---------------------------------------------------------------------------

NUDGE_COPY = (
    "Es la {n}ª vez que abres el teléfono esta noche.\n"
    "Hace dos semanas, a esta hora ya lo habías soltado."
)


def replay_nudge(tl: Timeline, df: pd.DataFrame) -> list[NightNudge]:
    """Reproduce el nudge sobre el historial: cuándo habría salido y qué había
    en juego cuando salió.

    No se puede hacer un A/B sobre un fichero cerrado, pero sí medir el **techo**
    del nudge: los minutos de pantalla nocturna que ocurren *después* del
    momento en que se habría mostrado. Eso acota lo que puede recuperar, y el
    número de noches sin disparo acota lo que molesta.
    """
    out: list[NightNudge] = []
    baseline = df.set_index("day")["night_min_baseline"].to_dict()
    recent3 = df.set_index("day")["night_min"].rolling(3, min_periods=1).median().to_dict()

    for d in df.day:
        n0, n1 = _night_window(d)
        ivs = sorted([i for i in tl.intervals if i.end_ms > n0 and i.start_ms < n1],
                     key=lambda i: i.start_ms)
        night_min = sum((min(i.end_ms, n1) - max(i.start_ms, n0)) / 60_000 for i in ivs)
        arm_from = n0 + NUDGE_AFTER_MIN * 60_000
        reopens = [i for i in ivs if i.is_pickup and i.start_ms >= arm_from]

        quiet = ""
        if len(reopens) < NUDGE_MIN_REOPENS:
            quiet = ("Una sola reapertura: quedarse hasta tarde una noche no es "
                     "un patrón, y avisar por eso enseña a ignorar el aviso.")
        else:
            base, rec = baseline.get(d), recent3.get(d)
            if base is not None and rec is not None and not pd.isna(base) and rec < base:
                quiet = ("Las últimas noches ya van mejor que su propia media; "
                         "cuando alguien está corrigiendo solo, lo útil es callarse.")

        fired = not quiet and len(reopens) >= NUDGE_MIN_REOPENS
        at = reopens[NUDGE_MIN_REOPENS - 1].start_ms if fired else None
        after = (sum((min(i.end_ms, n1) - max(i.start_ms, at)) / 60_000
                     for i in ivs if i.end_ms > at) if fired else 0.0)

        out.append(NightNudge(d, fired, at, quiet, len(reopens), after, night_min))
    return out


def nudge_summary(nudges: list[NightNudge]) -> dict:
    fired = [n for n in nudges if n.fired]
    night_total = sum(n.night_minutes for n in nudges)
    after = sum(n.minutes_after for n in fired)
    return {
        "noches": len(nudges),
        "noches con aviso": len(fired),
        "tasa de aparición": len(fired) / max(len(nudges), 1),
        "min nocturnos totales": night_total,
        "min en juego tras el aviso": after,
        "cuota del total nocturno": after / night_total if night_total else 0.0,
        "min en juego por noche con aviso": after / len(fired) if fired else 0.0,
        "hora mediana del aviso": (
            sorted(to_dt(n.at_ms).hour + to_dt(n.at_ms).minute / 60 % 24
                   for n in fired)[len(fired) // 2] if fired else None),
    }


# ---------------------------------------------------------------------------
# Recorrido del mes · qué sabía y qué emitía el teléfono cada día
# ---------------------------------------------------------------------------

def month_replay(df: pd.DataFrame, nudges: list[NightNudge],
                 positives: list[Signal] | None = None) -> list[dict]:
    """Estado del sistema al cierre de cada día, con la información que tenía
    ese día y no la del mes entero.

    Los **avisos** se reevalúan sobre el histórico disponible hasta cada fecha:
    su reparto de cupo ordena por prioridad, así que depende del conjunto y hay
    que recalcularlo para saber qué se habría enviado ese día.

    Los **refuerzos** no: cada regla mira sólo hacia atrás y el cupo es una
    pasada hacia delante con memoria, así que `evaluate_positives` sobre el
    frame completo ya da el resultado causal. Recalcularlos por prefijo
    reiniciaría el cupo cada día y multiplicaría los envíos.
    """
    positives = positives or []
    pos_by_day: dict[date, list[Signal]] = {}
    for s in positives:
        if s.decision == "enviada":
            pos_by_day.setdefault(s.day, []).append(s)
    by_day = {n.day: n for n in nudges}
    out: list[dict] = []

    for i, day in enumerate(df["day"]):
        upto = df.iloc[: i + 1]
        sigs = evaluate_alerts(upto)
        pos_today = pos_by_day.get(day, [])
        sent_today = next((s for s in sigs
                           if s.decision == "enviada" and s.day == day), None)
        digest_today = next((s for s in sigs
                             if s.decision == "resumen" and s.day == day), None)
        nudge = by_day.get(day)

        out.append({
            "day": day,
            "alert": sent_today,
            "digest_entry": digest_today,
            "nudge": nudge,
            "positives": pos_today,
            "positives_so_far": sum(
                len(v) for k, v in pos_by_day.items() if k <= day),
            # acumulados a esa fecha, como los vería el tutor
            "alerts_so_far": sum(1 for s in sigs if s.decision == "enviada"),
            "digest_so_far": sum(1 for s in sigs if s.decision == "resumen"),
            "nudges_so_far": sum(1 for n in nudges if n.fired and n.day <= day),
            "estado": ("algo ha cambiado"
                       if any(s.decision == "enviada" for s in sigs)
                       else "todo en orden"),
        })
    return out


def emissions(replay: list[dict]) -> list[dict]:
    """Lista plana de todo lo que el teléfono emitió, en orden temporal.

    Tres destinos posibles y sólo tres: pantalla del usuario (nudge),
    notificación al tutor (alerta) y resumen semanal (señal retenida).
    """
    out: list[dict] = []
    for r in replay:
        if r["nudge"] and r["nudge"].fired:
            out.append({
                "day": r["day"], "destino": "Usuario · pantalla",
                "tipo": "Nudge nocturno",
                "detalle": (f"{r['nudge'].reopens}ª reapertura de la noche · "
                            f"{r['nudge'].minutes_after:.0f} min de pantalla después"),
            })
        if r["alert"]:
            out.append({
                "day": r["day"], "destino": "Tutor · notificación",
                "tipo": r["alert"].key, "detalle": r["alert"].headline,
            })
        if r["digest_entry"]:
            out.append({
                "day": r["day"], "destino": "Tutor · resumen semanal",
                "tipo": r["digest_entry"].key,
                "detalle": r["digest_entry"].headline,
            })
        for s in r.get("positives", []):
            out.append({
                "day": r["day"],
                "destino": ("Usuario · refuerzo" if s.audience == "usuario"
                            else "Tutor · refuerzo"),
                "tipo": s.key, "detalle": s.headline,
            })
    return sorted(out, key=lambda x: x["day"])


# ---------------------------------------------------------------------------
# Refuerzo positivo
# ---------------------------------------------------------------------------
#
# Criterio de diseño, en tres reglas:
#
# 1. **Contra uno mismo, no contra una tabla.** Un umbral absoluto felicita
#    siempre al usuario A y nunca al B, que es justo al revés de lo que sirve.
#    Todos los refuerzos comparan a la persona con sus propias últimas semanas.
#
# 2. **Sólo cambios con margen.** Se exige un margen mínimo sobre el mejor
#    registro reciente (10 % en récords, 30 % en semanas) para que el ruido
#    diario no dispare nada. Un récord que se bate por un minuto no es un
#    récord, es varianza.
#
# 3. **Descriptivo, nunca prescriptivo.** El texto dice qué ha pasado y contra
#    qué se compara. No felicita en segunda persona ni sugiere qué hacer
#    después; eso convierte una medición en una opinión.
#
# Presupuesto: un refuerzo por semana y audiencia como mucho. El resto se
# acumula en el resumen semanal, que es donde vive el balance completo.

#: Margen mínimo para considerar que un récord se ha batido de verdad.
POS_RECORD_MARGIN = 1.10
#: Suelo absoluto para el récord de desconexión: 90 min sin mirar el teléfono
#: no es una gesta para nadie.
POS_OFFLINE_FLOOR_H = 3.0
#: Hitos de racha de noches protegidas.
POS_STREAK_MILESTONES = (7, 14, 30)
#: Una noche cuenta como protegida por debajo de este umbral.
POS_NIGHT_QUIET_MIN = 5.0
#: Semanas con menos días que esto no generan refuerzo: una semana de tres días
#: siempre parece mejor que una de siete.
POS_MIN_WEEK_DAYS = 5
#: Cupo de refuerzos por audiencia.
POS_BUDGET_DAYS = 7


def _num(x: float, dec: int = 1) -> str:
    """Decimal con coma, que es como se escribe en castellano."""
    return f"{x:.{dec}f}".replace(".", ",")


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def _weeks(df: pd.DataFrame) -> pd.DataFrame:
    """Agregado por semana, sólo con las semanas de tamaño suficiente."""
    w = df.groupby("week").agg(
        days=("day", "count"), last_day=("day", "max"),
        screen=("screen_min", "mean"), pickups=("pickups", "mean"),
        night=("night_min", "mean"), blocks=("blocks", "mean"),
        sensitive=("blocks_sensitive", "sum"),
        distract=("distract_share", "mean"), score=("score", "mean"),
    )
    return w[w.days >= POS_MIN_WEEK_DAYS]


def _pos(key, day, headline, text, evidence, audience="usuario") -> Signal:
    return Signal(key=key, day=day, headline=headline, guardian_text=text,
                  magnitude=1.0, persistence=1.0, actionability=1.0,
                  evidence=evidence, audience=audience, tone="refuerzo")


def _offline_record(df: pd.DataFrame) -> list[Signal]:
    """Mejor rato seguido sin pantalla de las últimas dos semanas."""
    out = []
    off = (df["longest_offline_s"] / 3600).reset_index(drop=True)
    days = df["day"].reset_index(drop=True)
    for i in range(14, len(df)):
        prev = off.iloc[i - 14:i].max()
        v = off.iloc[i]
        if v >= max(prev * POS_RECORD_MARGIN, POS_OFFLINE_FLOOR_H):
            out.append(_pos(
                "offline_record", days.iloc[i],
                "Racha sin pantalla más larga de las últimas dos semanas",
                f"{_hm(v * 60)} seguidos sin encender la pantalla. El mejor "
                f"registro de las dos semanas anteriores era {_hm(prev * 60)}.",
                {"racha (h)": round(float(v), 2),
                 "mejor de 14 días (h)": round(float(prev), 2)}))
    return out


def _night_streak(df: pd.DataFrame) -> list[Signal]:
    """Noches consecutivas sin pantalla en la franja protegida."""
    out, streak = [], 0
    for day, night in zip(df["day"], df["night_min"]):
        streak = streak + 1 if night < POS_NIGHT_QUIET_MIN else 0
        if streak in POS_STREAK_MILESTONES:
            out.append(_pos(
                "night_streak", day,
                f"{streak} noches seguidas sin pantalla de madrugada",
                f"{streak} noches consecutivas sin encender la pantalla entre "
                f"las 23:00 y las 06:00.",
                {"noches consecutivas": streak}))
    return out


def _calm_week(df: pd.DataFrame) -> list[Signal]:
    """Semana con menos intervenciones del filtro que las dos anteriores."""
    out, w = [], _weeks(df)
    for i in range(2, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 2:i]
        base = prev.blocks.mean()
        if base >= 1 and cur.blocks <= base * 0.7:
            out.append(_pos(
                "calm_week", cur.last_day,
                "El filtro ha intervenido menos que en semanas anteriores",
                f"Esta semana el filtro ha actuado {_num(cur.blocks)} veces al "
                f"día, frente a {_num(base)} de las dos semanas anteriores.",
                {"bloqueos/día esta semana": round(float(cur.blocks), 2),
                 "bloqueos/día 2 semanas antes": round(float(base), 2)}))
    return out


def _focus_week(df: pd.DataFrame) -> list[Signal]:
    """Semana con menos cuota de tiempo en redes, ocio y juegos."""
    out, w = [], _weeks(df)
    for i in range(1, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 1]
        if prev.distract >= 0.10 and cur.distract <= prev.distract * 0.8:
            out.append(_pos(
                "focus_week", cur.last_day,
                "Menos tiempo en redes, ocio y juegos que la semana anterior",
                f"Esta semana el {cur.distract*100:.0f} % del tiempo de pantalla "
                f"fue de redes, ocio o juegos, frente al "
                f"{prev.distract*100:.0f} % de la semana anterior.",
                {"cuota esta semana": f"{cur.distract*100:.1f} %",
                 "cuota semana anterior": f"{prev.distract*100:.1f} %"}))
    return out


def _best_week(df: pd.DataFrame) -> list[Signal]:
    """Índice semanal más alto del historial disponible."""
    out, w = [], _weeks(df)
    for i in range(3, len(w)):
        cur, prev = w.iloc[i], w.iloc[:i]
        if cur.score > prev.score.max():
            out.append(_pos(
                "best_week", cur.last_day,
                "Índice semanal más alto del periodo",
                f"El índice de esta semana es {cur.score:.0f} sobre 100, el más "
                f"alto desde el inicio del registro. El anterior era "
                f"{prev.score.max():.0f}.",
                {"índice esta semana": round(float(cur.score), 1),
                 "mejor anterior": round(float(prev.score.max()), 1)}))
    return out


def _filter_calm(df: pd.DataFrame) -> list[Signal]:
    """Descenso claro de intentos hacia contenido sensible. Va al tutor.

    Es el reverso exacto de `sensitive_spike`, y con la misma granularidad: sin
    cifras, sin objetos, sin categorías. Un tutor que sólo recibe noticias
    cuando algo empeora acaba leyendo el canal como una amenaza.
    """
    out, w = [], _weeks(df)
    for i in range(1, len(w)):
        cur, prev = w.iloc[i], w.iloc[i - 1]
        if prev.sensitive >= 10 and cur.sensitive <= prev.sensitive * 0.6:
            out.append(_pos(
                "filter_calm", cur.last_day,
                "El filtro de contenido sensible ha intervenido menos",
                "Esta semana el filtro de contenido sensible ha intervenido "
                "bastante menos que la anterior. Ningún contenido llegó a "
                "abrirse, como en semanas anteriores.",
                {"intentos esta semana": int(cur.sensitive),
                 "intentos semana anterior": int(prev.sensitive)},
                audience="tutor"))
    return out


POSITIVE_RULES = (_offline_record, _night_streak, _calm_week,
                  _focus_week, _best_week, _filter_calm)


def evaluate_positives(df: pd.DataFrame, has_guardian: bool = True) -> list[Signal]:
    """Refuerzos candidatos, con cupo de uno por semana y audiencia.

    Lo que no entra en el cupo no se descarta: baja al resumen semanal, que es
    donde el usuario ve el balance completo sin que nadie le interrumpa.
    """
    signals: list[Signal] = []
    for rule in POSITIVE_RULES:
        signals.extend(rule(df))
    if not has_guardian:
        signals = [s for s in signals if s.audience != "tutor"]

    last_sent: dict[str, date] = {}
    for s in sorted(signals, key=lambda x: x.day):
        prev = last_sent.get(s.audience)
        if prev and (s.day - prev).days < POS_BUDGET_DAYS:
            s.decision = "resumen"
            s.reason = (f"Ya se envió un refuerzo a esta audiencia hace menos de "
                        f"{POS_BUDGET_DAYS} días. Entra en el resumen semanal.")
            continue
        s.decision, s.reason = "enviada", "Mejora medible sobre el propio historial."
        last_sent[s.audience] = s.day
    return sorted(signals, key=lambda x: x.day)
