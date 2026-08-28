"""
Balance · explorador de comportamiento de dispositivo.

Dashboard de lectura: qué hay en los eventos, qué métricas salen de ahí, y qué
historia cuentan los dos usuarios del mes de mayo de 2026.

    streamlit run app.py
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from balance import charts, theme
from balance.events import SENSITIVE, load
from balance.metrics import (
    blocks_frame, category_daily, daily_frame, hourly_heat, totals, weekly_frame,
)
from balance.intelligence import (
    ALERT_BUDGET, NUDGE_AFTER_MIN, emissions, evaluate_alerts,
    evaluate_positives, month_replay, nudge_summary, replay_nudge,
)
from balance.score import COMPONENTS, add_score, contributions

st.set_page_config(page_title="Balance · Explorador de eventos",
                   page_icon="◐", layout="wide",
                   initial_sidebar_state="expanded")
theme.register_template()
st.markdown(theme.CSS, unsafe_allow_html=True)
st.markdown(theme.PHONE_CSS, unsafe_allow_html=True)

DATA = {"A": "data/events_user_a.json", "B": "data/events_user_b.json"}

#: Sólo el perfil B tiene tutor asignado. El A es un adulto: sus reglas de
#: aviso existen igual, pero no hay destinatario al que notificar, así que sus
#: señales sólo alimentan su propio índice y sus nudges.
HAS_GUARDIAN = {"A": False, "B": True}


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Reconstruyendo sesiones desde los eventos…")
def build(user: str):
    tl = load(DATA[user], user)
    df = add_score(daily_frame(tl))
    # los días truncados por el borde del fichero quedan fuera de TODAS las
    # vistas, no sólo del frame diario, o los totales dejan de cuadrar.
    days = set(df["day"])
    nudges = replay_nudge(tl, df)
    positives = evaluate_positives(df, HAS_GUARDIAN[user])
    replay = month_replay(df, nudges, positives)

    weekly = weekly_frame(df)
    for col, *_ in COMPONENTS:
        weekly[f"score_{col}"] = df.groupby("week")[f"score_{col}"].mean()

    return {
        "df": df,
        "apps": totals(tl, df, "app"),
        "sites": totals(tl, df, "site"),
        "cats": category_daily(df),
        "heat": hourly_heat(tl, days),
        "blocks": blocks_frame(tl, days),
        "events": tl.events,
        "anomalies": dict(tl.anomalies),
        "n_intervals": len(tl.intervals),
        "screen_h": sum(i.seconds for i in tl.intervals) / 3600,
        "attributed_h": sum(u.seconds for u in tl.usages) / 3600,
        "alerts": evaluate_alerts(df),
        "positives": positives,
        "weekly": weekly,
        "nudges": nudges,
        "replay": replay,
        "emissions": emissions(replay),
    }


U = {u: build(u) for u in DATA}
F = {u: U[u]["df"] for u in DATA}


# ---------------------------------------------------------------------------
# Helpers de presentación
# ---------------------------------------------------------------------------

def note(text: str, kind: str = "") -> None:
    st.markdown(f'<div class="note {kind}">{text}</div>', unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def empty_box(text: str) -> None:
    """Hueco explícito. Un teléfono dibujado diciendo «no se muestra nada» es
    una notificación que dice que no hay notificación: ocupa lo mismo y se lee
    igual de fuerte que las que sí existen."""
    st.markdown(f'<div class="empty">{text}</div>', unsafe_allow_html=True)


MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha(d) -> str:
    """`%b` sale en inglés salvo que se toque el locale del proceso, cosa que
    no merece la pena hacer sólo para tres etiquetas."""
    return f"{d.day} {MESES[d.month - 1]}"


def reloj(h) -> str:
    """Hora del eje desplazado (24 a 28 = madrugada) a HH:MM. Es None cuando no
    hubo ninguna pantalla en la franja, que es el caso normal del usuario A."""
    if h is None or pd.isna(h):
        return "sin uso"
    return f"{int(h % 24):02d}:{int(h % 1 * 60):02d}"


def hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def kpis(items: list[tuple[str, str, str | None]]) -> None:
    for col, (label, value, delta) in zip(st.columns(len(items)), items):
        col.metric(label, value, delta, delta_color="off" if delta else "normal")


def wk(df: pd.DataFrame, col: str, week: int, how: str = "mean") -> float:
    s = df[df["week"] == week][col]
    return getattr(s, how)()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("Balance")
    st.caption("Explorador de eventos de dispositivo · mayo 2026")
    st.markdown("---")
    eyebrow("Huella de datos")
    for u in DATA:
        st.caption(
            f"**Usuario {u}**: {len(U[u]['events']):,} eventos · "
            f"{len(F[u])} días completos · {U[u]['n_intervals']} tramos de pantalla"
        )
    st.markdown("---")
    eyebrow("Alcance de los datos")
    st.caption(
        "Vista de dispositivo. El detalle por app, por sitio y de bloqueos no se "
        "transmite fuera del teléfono. Lo que recibe un tutor está en "
        "**Alertas y nudges**."
    )
    st.markdown("---")
    eyebrow("Notificaciones del periodo")
    for u in DATA:
        n = (sum(1 for x in U[u]["alerts"] if x.decision == "enviada")
             if HAS_GUARDIAN[u] else None)
        st.caption(f"**Usuario {u}**: "
                   f"{f'{n} al tutor' if n is not None else 'sin tutor'} · "
                   f"{sum(1 for x in U[u]['nudges'] if x.fired)} nudges")


st.title("Comportamiento de dispositivo · mayo 2026")
st.caption(
    "2 perfiles · 11.488 eventos · 30 días · tiempo de pantalla, desbloqueos, "
    "franja nocturna, categorías, bloqueos, índice de bienestar y avisos"
)

# El selector vive en el cuerpo, no en la barra lateral: si alguien la cierra,
# poder cambiar de perfil no debería depender de encontrar el botón de
# reabrirla. La barra lateral se queda sólo con contexto.
_sel, _rest = st.columns([1, 4])
with _sel:
    who = st.radio(
        "Perfil a inspeccionar", ["A", "B"], horizontal=True, key="who",
        help="Afecta a Ritmo diario, En qué se va el tiempo y Lo que el teléfono "
             "paró. Panorama y La noche siempre comparan los dos.",
    )

TABS = st.tabs([
    "Panorama", "Resumen semanal", "Ritmo diario", "La noche",
    "En qué se va el tiempo", "Lo que el teléfono paró", "Alertas y nudges",
    "Los datos",
])


# ===========================================================================
# 1 · PANORAMA
# ===========================================================================
with TABS[0]:
    a, b = F["A"], F["B"]

    st.markdown("### Perfiles")
    note(
        f"Los dos ficheros corresponden a perfiles distintos y requieren "
        f"configuraciones distintas.<br><br>"
        f"<b>Usuario A</b> · adulto sin tutor. {hm(a.screen_min.mean())} de "
        f"pantalla al día, {a.pickups.mean():.0f} desbloqueos, "
        f"{a.distinct_apps.mean():.0f} apps. Sin uso nocturno y sin contenido "
        f"sensible en los 30 días.<br>"
        f"<b>Usuario B</b> · menor con tutor. {hm(b.screen_min.mean())}, "
        f"{b.pickups.mean():.0f} desbloqueos, {b.distinct_apps.mean():.0f} apps. "
        f"{b.blocks.sum():,.0f} intentos bloqueados, de los que "
        f"{b.blocks_sensitive.sum():.0f} son <code>ADULT</code> o "
        f"<code>GAMBLING</code>. Catálogo compatible con menor: Duolingo y Kindle "
        f"en uso diario, Roblox y Clash of Clans bloqueados 73 y 71 veces."
    )

    c1, c2 = st.columns(2)
    for col, u in ((c1, "A"), (c2, "B")):
        d = F[u]
        with col:
            eyebrow(f"Usuario {u} · índice de bienestar")
            st.markdown(
                f"<div style='font-family:{theme.MONO};font-size:3.4rem;"
                f"line-height:1;color:{theme.USER_COLOR[u]};font-weight:600'>"
                f"{d.score.mean():.0f}<span style='font-size:1.1rem;color:{theme.MUTED}'>"
                f" /100</span></div>"
                f"<div class='eyebrow' style='margin-top:.35rem'>"
                f"semana 1 → {wk(d,'score',1):.0f} &nbsp;·&nbsp; última semana completa → "
                f"{wk(d,'score',4):.0f}</div>",
                unsafe_allow_html=True)

    st.markdown("")
    kpis([
        ("A · pantalla/día", hm(a.screen_min.mean()), None),
        ("A · desbloqueos/día", f"{a.pickups.mean():.0f}", None),
        ("A · madrugada/día", f"{a.night_min.mean():.0f} min", None),
        ("A · bloqueos/mes", f"{a.blocks.sum():.0f}", None),
        ("A · sensibles", f"{a.blocks_sensitive.sum():.0f}", None),
    ])
    kpis([
        ("B · pantalla/día", hm(b.screen_min.mean()), None),
        ("B · desbloqueos/día", f"{b.pickups.mean():.0f}", None),
        ("B · madrugada/día", f"{b.night_min.mean():.0f} min", None),
        ("B · bloqueos/mes", f"{b.blocks.sum():,.0f}", None),
        ("B · sensibles", f"{b.blocks_sensitive.sum():.0f}", None),
    ])

    st.markdown("### Índice de bienestar")
    st.plotly_chart(charts.score_line(F), width="stretch", key="k_score")
    note(
        f"<b>A</b> se mantiene en {a.score.mean():.0f} las cuatro semanas "
        f"(rango {a.score.min():.0f} a {a.score.max():.0f}); sin cambio de "
        f"tendencia.<br>"
        f"<b>B</b> pasa de {wk(b,'score',1):.0f} a {wk(b,'score',4):.0f}, "
        f"{wk(b,'score',1)-wk(b,'score',4):.0f} puntos en tres semanas. La caída "
        f"viene casi entera del componente nocturno: su puntuación de noche baja "
        f"de {wk(b,'score_night_min',1):.0f} a {wk(b,'score_night_min',4):.0f} "
        f"mientras el resto de componentes se mueve menos de 10 puntos. Detalle "
        f"en «La noche».",
        "warn")

    st.markdown("### Lo que se mueve y lo que no")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(charts.compare_line(F, "screen_min",
                        "Tiempo de pantalla al día", "minutos"),
                        width="stretch", key="k_screen")
        st.plotly_chart(charts.compare_line(F, "pickups",
                        "Desbloqueos reales al día", "desbloqueos"),
                        width="stretch", key="k_pickups")
    with g2:
        st.plotly_chart(charts.compare_line(F, "night_min",
                        "Minutos de pantalla de madrugada", "minutos"),
                        width="stretch", key="k_night")
        st.plotly_chart(charts.compare_line(F, "blocks",
                        "Intentos bloqueados al día", "bloqueos"),
                        width="stretch", key="k_blocks")

    d_screen = (wk(b, "screen_min", 4) / wk(b, "screen_min", 1) - 1) * 100
    d_pick = (wk(b, "pickups", 4) / wk(b, "pickups", 1) - 1) * 100
    d_night = wk(b, "night_min", 4) / max(wk(b, "night_min", 1), .01)
    st.markdown("### Variación de B entre la semana 1 y la 4")
    st.dataframe(pd.DataFrame([
        ("Pantalla al día", f"{wk(b,'screen_min',1):.0f} min",
         f"{wk(b,'screen_min',4):.0f} min", f"{d_screen:+.0f} %"),
        ("Desbloqueos al día", f"{wk(b,'pickups',1):.0f}",
         f"{wk(b,'pickups',4):.0f}", f"{d_pick:+.0f} %"),
        ("Minutos de madrugada", f"{wk(b,'night_min',1):.1f} min",
         f"{wk(b,'night_min',4):.0f} min", f"×{d_night:.0f}"),
        ("Desbloqueos tras medianoche", f"{wk(b,'night_pickups',1):.1f}",
         f"{wk(b,'night_pickups',4):.1f}",
         f"×{wk(b,'night_pickups',4)/max(wk(b,'night_pickups',1),.01):.0f}"),
        ("Bloqueos al día", f"{wk(b,'blocks',1):.0f}",
         f"{wk(b,'blocks',4):.0f}",
         f"{(wk(b,'blocks',4)/wk(b,'blocks',1)-1)*100:+.0f} %"),
    ], columns=["Métrica", "Semana 1", "Semana 4", "Variación"]),
        width="stretch", hide_index=True)
    note(
        f"El volumen apenas se mueve ({d_screen:+.0f} % de pantalla, "
        f"{d_pick:+.0f} % de desbloqueos) y el horario nocturno se multiplica por "
        f"{d_night:.0f}. Un umbral sobre tiempo de pantalla no habría detectado "
        f"este caso: la detección va sobre la franja nocturna, no sobre el total "
        f"(ver «Alertas y nudges»).",
        "serious")

# ===========================================================================
# 2 · RESUMEN SEMANAL
# ===========================================================================
with TABS[1]:
    d = F[who]
    w = U[who]["weekly"]
    st.markdown(f"### Usuario {who} · resumen por semana")

    weeks = list(w.index)
    sel = st.select_slider(
        "Semana", options=weeks, value=weeks[-2] if len(weeks) > 1 else weeks[-1],
        format_func=lambda i: (f"Semana {i}"
                               + (" (parcial)" if w.loc[i, "is_partial"] else "")),
        key=f"week_{who}")
    cur = w.loc[sel]
    prev = w.loc[sel - 1] if sel - 1 in w.index else None

    st.caption(
        f"Del {fecha(cur['start'])} al {fecha(cur['end'])} · {int(cur['days'])} "
        f"días" + ("  ·  semana incompleta: las medias son por día, pero la "
                   "comparación con semanas de siete días es menos fiable."
                   if cur["is_partial"] else "")
    )

    def delta(col, unit="", dec=0):
        """Variación frente a la semana anterior, en la unidad de la métrica.

        Una variación que redondea a cero no se muestra: «+0 min» con flecha
        verde dice que algo ha mejorado cuando no se ha movido nada.
        """
        if prev is None or pd.isna(prev[col]):
            return None
        v = cur[col] - prev[col]
        if abs(round(v, dec)) < 10 ** -dec / 2 or f"{v:.{dec}f}".strip("-+") in ("0", "0.0"):
            return "sin cambio"
        return f"{v:+.{dec}f} {unit}".strip()

    kpis([
        ("Pantalla / día", hm(cur["screen_min"]), delta("screen_min", "min")),
        ("Desbloqueos / día", f"{cur['pickups']:.0f}", delta("pickups")),
        ("Madrugada / noche", f"{cur['night_min']:.0f} min",
         delta("night_min", "min")),
        ("Desconexión más larga", f"{cur['longest_offline_h']:.1f} h",
         delta("longest_offline_h", "h", dec=1)),
        ("Mejor racha de la semana", f"{cur['best_offline_h']:.1f} h",
         cur["best_offline_when"]),
        ("Bloqueos / día", f"{cur['blocks']:.1f}", delta("blocks", dec=1)),
        ("Índice", f"{cur['score']:.0f}", delta("score", dec=0)),
    ])

    st.markdown("")
    g1, g2 = st.columns(2)
    with g1:
        st.plotly_chart(charts.week_evolution(
            w, "screen_min", "Pantalla al día, por semana", "min", who, sel),
            width="stretch", key=f"we_screen_{who}")
        st.plotly_chart(charts.week_evolution(
            w, "night_min", "Madrugada por noche, por semana", "min", who, sel),
            width="stretch", key=f"we_night_{who}")
    with g2:
        st.plotly_chart(charts.week_evolution(
            w, "pickups", "Desbloqueos al día, por semana", "", who, sel),
            width="stretch", key=f"we_pick_{who}")
        st.plotly_chart(charts.week_evolution(
            w, "blocks", "Bloqueos al día, por semana", "", who, sel),
            width="stretch", key=f"we_blocks_{who}")
    st.caption("Las semanas marcadas con * no llegan a siete días.")

    st.plotly_chart(charts.week_components(w, sel), width="stretch",
                    key=f"we_comp_{who}")

    st.markdown(f"#### Los días de la semana {sel}")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.week_days(
            d, sel, "screen_min", f"Pantalla al día · semana {sel}", "min", who),
            width="stretch", key=f"wd_screen_{who}")
    with c2:
        st.plotly_chart(charts.week_days(
            d, sel, "night_min", f"Madrugada por noche · semana {sel}", "min", who),
            width="stretch", key=f"wd_night_{who}")

    st.markdown("#### Comparación con el resto del periodo")
    rows = [
        ("Pantalla al día", "screen_min", "min", 0),
        ("Desbloqueos al día", "pickups", "", 0),
        ("Madrugada por noche", "night_min", "min", 0),
        ("Desconexión más larga", "longest_offline_h", "h", 1),
        ("Apps distintas al día", "distinct_apps", "", 1),
        ("Cambios de app por hora", "switches_per_screen_hour", "", 0),
        ("Cuota de distracción", "distract_share", "%", 0),
        ("Bloqueos al día", "blocks", "", 1),
        ("Índice", "score", "", 0),
    ]
    tbl = []
    for label, col, unit, dec in rows:
        mult = 100 if unit == "%" else 1
        # Se redondea ANTES de restar: si no, la variación no cuadra con las
        # dos columnas que tiene al lado y parece un error de cálculo.
        v = round(cur[col] * mult, dec)
        pv = (round(prev[col] * mult, dec)
              if prev is not None and not pd.isna(prev[col]) else None)
        med = round(w[col].median() * mult, dec)
        if pv is None:
            var = "n/a"
        elif abs(v - pv) < 10 ** -dec / 2:
            var = "sin cambio"
        else:
            var = f"{v - pv:+.{dec}f} {unit}".strip()
        tbl.append({
            "Métrica": label,
            f"Semana {sel}": f"{v:.{dec}f} {unit}".strip(),
            "Semana anterior": (f"{pv:.{dec}f} {unit}".strip()
                                if pv is not None else "n/a"),
            "Mediana del periodo": f"{med:.{dec}f} {unit}".strip(),
            "Variación": var,
        })
    st.dataframe(pd.DataFrame(tbl), width="stretch", hide_index=True)

    st.markdown(f"#### Lo que el teléfono emitió en la semana {sel}")
    wk_days = set(d[d["week"] == sel]["day"])
    wk_em = [e for e in U[who]["emissions"] if e["day"] in wk_days]
    resumen = [x for x in U[who]["positives"]
               if x.decision == "resumen" and x.day in wk_days]

    if wk_em:
        st.dataframe(pd.DataFrame([{
            "Fecha": fecha(e["day"]), "Destino": e["destino"],
            "Tipo": e["tipo"], "Detalle": e["detalle"],
        } for e in wk_em]), width="stretch", hide_index=True)
    else:
        st.caption("Ninguna notificación ni nudge en esta semana.")

    if resumen:
        st.markdown("**También registrado esta semana, sin notificar**")
        for x in resumen:
            st.markdown(
                f"<div class='phone-row'><span>{x.headline}</span>"
                f"<span>{x.reason.split('.')[0]}</span></div>",
                unsafe_allow_html=True)


# ===========================================================================
# 3 · RITMO DIARIO
# ===========================================================================
with TABS[2]:
    d = F[who]
    st.markdown(f"### Usuario {who} · resumen del mes")

    best = d.loc[d.score.idxmax()]
    worst = d.loc[d.score.idxmin()]
    kpis([
        ("Pantalla / día", hm(d.screen_min.mean()),
         f"±{d.screen_min.std():.0f} min"),
        ("Sesiones / día", f"{d.sessions.mean():.0f}",
         f"mediana {d.median_session_s.mean()/60:.1f} min"),
        ("Desbloqueos reales", f"{d.pickups.mean():.0f}",
         f"{d.glances.mean():.0f} vistazos"),
        ("Primer desbloqueo", d.first_pickup_clock.mode().iloc[0],
         f"mediana {d.first_pickup_h.median():.1f} h"),
        ("Desconexión más larga", f"{d.longest_offline_s.mean()/3600:.1f} h",
         f"mejor: {d.longest_offline_h.max():.1f} h "
         f"{d.loc[d.longest_offline_h.idxmax(), 'longest_offline_when']}"),
        ("Cambios de app / h", f"{d.switches_per_screen_hour.mean():.0f}",
         f"{d.distinct_apps.mean():.0f} apps distintas"),
    ])

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.daily_bars_vs_baseline(
            d, "screen_min", "screen_min_baseline",
            f"Usuario {who} · pantalla al día", "minutos", who),
            width="stretch", key="k_bar_screen")
    with c2:
        st.plotly_chart(charts.daily_bars_vs_baseline(
            d, "pickups", "pickups_baseline",
            f"Usuario {who} · desbloqueos al día",
            "desbloqueos", who), width="stretch", key="k_bar_pickups")
    st.caption(
        "Referencia: mediana de los 14 días anteriores del mismo usuario. Los 14 "
        "primeros días del periodo no tienen historial suficiente y se muestran "
        "sin comparar."
    )

    c3, c4 = st.columns(2)
    with c3:
        st.plotly_chart(charts.hour_heat(U[who]["heat"], who),
                        width="stretch", key="k_heat")
    with c4:
        st.plotly_chart(charts.day_span(d, who), width="stretch", key="k_span")

    wknd = d.groupby("is_weekend")[["screen_min", "pickups", "night_min"]].mean()
    diff = wknd.loc[True, "screen_min"] - wknd.loc[False, "screen_min"]
    if who == "A":
        note(
            f"<b>Rutina estable.</b> Primer desbloqueo entre las 07:30 y las 09:00, "
            f"última pantalla sobre las {d.last_use_clock.mode().iloc[0]}, sin "
            f"actividad después de las 23:00 en ningún día del periodo.<br><br>"
            f"<b>Uso laboral.</b> El fin de semana baja a "
            f"{wknd.loc[True,'screen_min']:.0f} min frente a "
            f"{wknd.loc[False,'screen_min']:.0f} entre semana "
            f"({abs(diff):.0f} min menos), con "
            f"{wknd.loc[False,'pickups']-wknd.loc[True,'pickups']:.0f} desbloqueos "
            f"menos.<br><br>"
            f"<b>Sesiones cortas y limpias.</b> Mediana de "
            f"{d.median_session_s.mean()/60:.1f} min y "
            f"{d.switches_per_screen_hour.mean():.0f} cambios de app por hora de "
            f"pantalla, sobre {d.distinct_apps.mean():.0f} apps distintas al día. "
            f"No requiere intervención.",
            "good")
    else:
        note(
            f"<b>Sin corte de fin de semana.</b> "
            f"{wknd.loc[True,'screen_min']:.0f} min en fin de semana frente a "
            f"{wknd.loc[False,'screen_min']:.0f} entre semana ({diff:+.0f}). "
            f"El uso está repartido de 08:00 a 00:00 los siete días, con la banda "
            f"de medianoche ganando peso a lo largo del mes.<br><br>"
            f"<b>Uso fragmentado.</b> Sesiones de "
            f"{d.median_session_s.mean()/60:.1f} min de mediana pero "
            f"{d.switches_per_screen_hour.mean():.0f} cambios de app por hora, "
            f"{d.switches_per_screen_hour.mean()/F['A'].switches_per_screen_hour.mean():.1f}× "
            f"la tasa del usuario A. El patrón es de consulta frecuente, no de "
            f"sesiones largas.<br><br>"
            f"<b>Franja nocturna activa.</b> {d.night_min.mean():.0f} min de media "
            f"entre las 23:00 y las 06:00, con tendencia creciente. Es el punto "
            f"que ha generado el aviso al tutor.",
            "warn")

    with st.expander("Ver la tabla diaria completa"):
        cols = ["day", "score", "screen_min", "pickups", "glances", "sessions",
                "night_min", "night_pickups", "first_pickup_clock",
                "last_use_clock", "longest_offline_s", "longest_offline_when",
                "distinct_apps",
                "app_switches", "distract_share", "blocks", "blocks_sensitive"]
        show = d[cols].copy()
        show["longest_offline_s"] = (show["longest_offline_s"] / 3600).round(1)
        show = show.rename(columns={"longest_offline_s": "offline_max_h"})
        st.dataframe(show.round(1), width="stretch", hide_index=True)
        st.download_button("Descargar CSV",
                           d.drop(columns=["_cat_s", "_app_s", "_site_s"]).to_csv(index=False),
                           file_name=f"balance_daily_{who}.csv", mime="text/csv")


# ===========================================================================
# 4 · LA NOCHE
# ===========================================================================
with TABS[3]:
    b = F["B"]
    st.markdown("### Franja nocturna · usuario B")

    n1, n4 = wk(b, "night_min", 1), wk(b, "night_min", 4)
    e1, e4 = wk(b, "night_end_h", 1), wk(b, "night_end_h", 4)
    f1, f4 = wk(b, "first_pickup_h", 1), wk(b, "first_pickup_h", 4)
    sleep1 = (24 + f1) - e1
    sleep4 = (24 + f4) - e4

    kpis([
        ("B · madrugada sem. 1", f"{n1:.0f} min", None),
        ("B · madrugada sem. 4", f"{n4:.0f} min", f"×{n4/max(n1,.01):.0f}"),
        ("B · última pantalla sem. 1", f"{int(e1%24):02d}:{int(e1%1*60):02d}", None),
        ("B · última pantalla sem. 4", f"{int(e4%24):02d}:{int(e4%1*60):02d}",
         f"{(e4-e1)*60:+.0f} min"),
        ("B · primer desbloqueo", f"{int(f4):02d}:{int(f4%1*60):02d}",
         f"{(f4-f1)*60:+.0f} min"),
        ("B · ventana de sueño", f"{sleep4:.1f} h", f"{(sleep4-sleep1)*60:+.0f} min"),
    ])

    st.markdown("")
    st.plotly_chart(charts.night_drift(F), width="stretch", key="k_nightdrift")

    note(
        f"<b>La hora de acostarse se retrasa; la de levantarse no.</b><br><br>"
        f"Última pantalla: {int(e1%24):02d}:{int(e1%1*60):02d} en la semana 1, "
        f"{int(e4%24):02d}:{int(e4%1*60):02d} en la semana 4 "
        f"({(e4-e1)*60:.0f} min más tarde).<br>"
        f"Primer desbloqueo: {int(f1):02d}:{int(f1%1*60):02d} → "
        f"{int(f4):02d}:{int(f4%1*60):02d} ({(f4-f1)*60:+.0f} min).<br>"
        f"Ventana entre ambos: {sleep1:.1f} h → {sleep4:.1f} h, "
        f"<b>{abs(sleep4-sleep1)*60:.0f} min menos de descanso disponible por "
        f"noche</b>.<br><br>"
        f"Los desbloqueos después de medianoche pasan de "
        f"{wk(b,'night_pickups',1):.1f} a {wk(b,'night_pickups',4):.1f} por noche. "
        f"No es un día suelto que se alarga: son "
        f"{wk(b,'night_pickups',4):.0f} vueltas al teléfono cada madrugada.",
        "serious")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.day_span(b, "B"), width="stretch", key="k_span_night")
    with c2:
        st.plotly_chart(charts.compare_line(F, "night_pickups",
                        "Desbloqueos después de medianoche", "desbloqueos", 5),
                        width="stretch", key="k_nightpick")

    note(
        f"<b>Usuario A, mismo periodo:</b> 0,0 min de pantalla entre las 23:00 y "
        f"las 06:00 en los 30 días. Última pantalla a las "
        f"{int(F['A'].last_use_h.mean()):02d}:"
        f"{int(F['A'].last_use_h.mean()%1*60):02d} de media, sin reaperturas "
        f"posteriores. El corte de las 23:00 no penaliza a todos los perfiles por "
        f"igual: A lo respeta sin intervención del producto.",
        "good")

    st.markdown("### Peso de la noche en el índice")
    note(
        f"La franja nocturna pesa un 20 % del índice, lo mismo que la "
        f"fragmentación y más que la desconexión larga, pese a ser la métrica más "
        f"pequeña en valor absoluto ({b.night_min.mean():.0f} min de media frente "
        f"a {b.screen_min.mean():.0f} de pantalla total).<br><br>"
        f"El criterio: una hora de pantalla a la 01:00 sale del descanso y una "
        f"hora a las 17:00 no, y el margen de mejora es mucho más accesible. "
        f"Reducir dos horas de uso diario implica cambiar la rutina completa; "
        f"adelantar la última pantalla 40 minutos es un solo cambio."
    )

# ===========================================================================
# 5 · EN QUÉ SE VA EL TIEMPO
# ===========================================================================
with TABS[4]:
    d = F[who]
    apps, sites = U[who]["apps"], U[who]["sites"]
    st.markdown(f"### Usuario {who} · reparto del tiempo")

    st.markdown(
        '<span class="tag">sólo en el dispositivo</span>'
        '<span class="tag">nunca se envía al tutor</span>',
        unsafe_allow_html=True)

    top_share = apps.minutes.head(3).sum() / apps.minutes.sum() * 100
    kpis([
        ("Tiempo atribuido", f"{U[who]['attributed_h']:.0f} h",
         f"{U[who]['attributed_h']/U[who]['screen_h']*100:.0f} % de la pantalla"),
        ("Apps distintas", f"{len(apps)}", "en todo el mes"),
        ("Dominios distintos", f"{len(sites)}", "en todo el mes"),
        ("Top 3 apps", f"{top_share:.0f} %", "del tiempo en apps"),
        ("Cuota de distracción", f"{d.distract_share.mean()*100:.0f} %",
         "social + ocio + juegos"),
    ])

    st.markdown("")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(charts.top_bars(apps, f"Usuario {who} · apps por minutos"),
                        width="stretch", key="k_apps")
    with c2:
        st.plotly_chart(charts.top_bars(sites, f"Usuario {who} · dominios por minutos"),
                        width="stretch", key="k_sites")

    st.caption(
        "Color por categoría de contenido, misma escala que el gráfico inferior. "
        "Aperturas y minutos por apertura, en el tooltip y en la tabla completa."
    )

    st.plotly_chart(charts.category_area(
        U[who]["cats"], f"Usuario {who} · minutos por categoría de contenido"),
        width="stretch", key="k_cats")

    chrome = apps[apps.key == "com.android.chrome"]
    if who == "A":
        news = sites[sites.category == "NEWS"].minutes.sum() / sites.minutes.sum() * 100
        note(
            f"<b>Catálogo reducido.</b> {len(apps)} apps en 30 días: WhatsApp, "
            f"Spotify, Gmail, Maps, Teléfono y Calendario concentran casi todo, y "
            f"el top 3 se lleva el {top_share:.0f} % del tiempo en apps.<br><br>"
            f"<b>Navegación.</b> {news:.0f} % de los minutos son prensa "
            f"(bbc.com, elpais.com, elmundo.es, marca.com); el resto, compras "
            f"puntuales y consultas.<br><br>"
            f"<b>Distracción a la baja.</b> Media del "
            f"{d.distract_share.mean()*100:.0f} %, de "
            f"{wk(d,'distract_share',1)*100:.0f} % en la semana 1 a "
            f"{wk(d,'distract_share',4)*100:.0f} % en la 4.",
            "good")
        st.caption(
            f"Chrome aparece con {chrome.opens.iloc[0]:.0f} aperturas y sólo "
            f"{chrome.minutes.iloc[0]:.0f} min porque el tiempo de navegador se "
            f"atribuye al dominio visitado, no al navegador."
        )
    else:
        msg = apps[apps.category == "MESSAGING"].minutes.sum()
        note(
            f"<b>Uso disperso.</b> {len(apps)} apps frente a las "
            f"{len(U['A']['apps'])} del usuario A, y el top 3 concentra sólo el "
            f"{top_share:.0f} % del tiempo.<br><br>"
            f"<b>Mensajería en paralelo.</b> {msg:,.0f} min repartidos entre "
            f"WhatsApp, Mensajes y Telegram.<br><br>"
            f"<b>Cuota de distracción en rango normal.</b> "
            f"{d.distract_share.mean()*100:.0f} %, frente al "
            f"{F['A'].distract_share.mean()*100:.0f} % del usuario A. El reparto "
            f"por categorías no es el problema de este perfil; lo son el volumen "
            f"total y el horario.",
            "warn")
        st.caption(
            "Este gráfico sólo recoge contenido que llegó a abrirse. Roblox y "
            "Clash of Clans no aparecen pese a 75 y 71 intentos, porque el filtro "
            "dejó pasar 2 y 0 respectivamente. El detalle de intentos bloqueados "
            "está en «Lo que el teléfono paró»."
        )

    with st.expander("Tabla completa de apps y dominios"):
        c1, c2 = st.columns(2)
        c1.dataframe(apps.round(1), width="stretch", hide_index=True)
        c2.dataframe(sites.round(1), width="stretch", hide_index=True)


# ===========================================================================
# 6 · BLOQUEOS
# ===========================================================================
with TABS[5]:
    d = F[who]
    bf = U[who]["blocks"]
    st.markdown(f"### Usuario {who} · intentos bloqueados")

    st.markdown(
        '<span class="tag">sólo en el dispositivo</span>'
        '<span class="tag">al tutor sólo llega el agregado</span>',
        unsafe_allow_html=True)

    if bf.empty:
        st.info("Sin bloqueos en el periodo.")
    else:
        # La semana la asigna `daily_frame` y aquí sólo se consulta. Recalcularla
        # desde el primer día del frame se desviaría en cuanto el primer día del
        # fichero fuese parcial y quedase fuera.
        semana_de = dict(zip(d["day"], d["week"]))
        bf = bf.assign(week=[semana_de[x] for x in bf["day"]])
        sens = bf[bf.category.isin(SENSITIVE)]
        kpis([
            ("Intentos bloqueados", f"{len(bf):,}", f"{len(bf)/len(d):.1f} al día"),
            ("Apps bloqueadas", f"{d.blocks_app.sum():,}", None),
            ("Sitios bloqueados", f"{d.blocks_url.sum():,}", None),
            ("Detección de desnudos", f"{d.blocks_nudity.sum():,}", "en dispositivo"),
            ("Adulto + apuestas", f"{len(sens):,}",
             f"{len(sens)/max(len(bf),1)*100:.0f} % del total"),
            ("Llegaron a abrirse", "0", "de las sensibles"),
        ])

        st.markdown("")
        c1, c2 = st.columns([3, 2])
        with c1:
            st.plotly_chart(charts.blocks_daily(
                bf, f"Usuario {who} · intentos bloqueados por día"),
                width="stretch", key="k_blocks_daily")
        with c2:
            st.plotly_chart(charts.blocks_by_hour(
                bf, f"Usuario {who} · bloqueos por hora del día"),
                width="stretch", key="k_blocks_hour")

        # el mes no cae en semanas de 7: la última es una cola de 2 días y hay
        # que decirlo, o parece que los bloqueos se desploman al final.
        n_days = d.groupby("week").size()
        pivot = pd.crosstab(bf.category, bf.week)
        pivot.columns = [f"Semana {c} ({n_days[c]} d)" for c in pivot.columns]
        st.dataframe(pivot, width="stretch")

        if who == "A":
            note(
                f"<b>{len(bf)} intentos en 30 días</b>, todos de "
                f"<code>SOCIAL_MEDIA</code> y <code>ENTERTAINMENT</code>. Cero "
                f"contenido sensible en el periodo.<br><br>"
                f"<b>Tendencia a la baja:</b> {wk(d,'blocks',1,'sum'):.0f} "
                f"bloqueos en la semana 1, {wk(d,'blocks',4,'sum'):.0f} en la "
                f"semana 4. El filtro interviene cada vez menos, lo que indica que "
                f"el hábito de apertura se ha desplazado y no sólo que la barrera "
                f"lo esté conteniendo.<br><br>"
                f"Este perfil no requiere acción ni genera avisos.",
                "good")
        else:
            adult = bf[bf.category == "ADULT"]
            gamb = bf[bf.category == "GAMBLING"]
            nud = bf[bf.block_type == "NUDITY"]
            wk23 = len(sens[sens.week.isin([2, 3])])
            note(
                f"<b>Distracción ordinaria: {len(bf)-len(sens):,} intentos</b>, en "
                f"aumento ({wk(d,'blocks',1,'sum'):.0f} → "
                f"{wk(d,'blocks',4,'sum'):.0f} por semana). Social y ocio, "
                f"principalmente.<br><br>"
                f"<b>Contenido sensible: {len(adult)} intentos de contenido adulto "
                f"y {len(gamb)} de apuestas</b>, con {len(nud)} detecciones de "
                f"desnudos en dispositivo. Todos bloqueados; ninguno llegó a "
                f"abrirse.<br><br>"
                f"<b>Forma temporal: pico, no tendencia.</b> {wk23} de los "
                f"{len(sens)} intentos sensibles ({wk23/len(sens)*100:.0f} %) caen "
                f"en las semanas 2 y 3; en la 4 bajan a "
                f"{len(sens[sens.week==4])}.<br><br>"
                f"<b>Persistencia baja.</b> Agrupados en ráfagas de 10 minutos: "
                f"1,2 intentos de media, máximo 3. El patrón es de intento "
                f"aislado seguido de abandono, no de insistencia sobre el mismo "
                f"contenido. Por eso este bloque no genera notificación inmediata "
                f"al tutor, sino entrada en el resumen semanal "
                f"(ver «Alertas y nudges»).",
                "warn")

    st.markdown("### Alcance de estos datos")
    note(
        "Esta pestaña es vista de dispositivo. Los nombres de app y dominio, los "
        "conteos por objeto y las horas exactas no se transmiten a ningún tutor ni "
        "a ningún servidor.<br><br>"
        "En perfiles con tutor, lo que sí puede salir en su resumen es el estado "
        "agregado del "
        "filtro (<i>«actuó como de costumbre»</i> / <i>«actuó más de lo "
        "habitual»</i>) y el hecho de que "
        f"<b>{len(bf[bf.category.isin(SENSITIVE)]) if not bf.empty else 0} intentos "
        f"de contenido sensible fueron bloqueados y ninguno llegó a abrirse</b>. "
        "Comprobado sobre el stream: no hay ningún <code>URL_VISIT</code> ni "
        "<code>APP_FOREGROUND</code> con categoría <code>ADULT</code> o "
        "<code>GAMBLING</code> en ninguno de los dos ficheros."
    )

# ===========================================================================
# 7 · ALERTAS Y NUDGES
# ===========================================================================
with TABS[6]:
    d = F[who]
    sigs = U[who]["alerts"]
    nud = U[who]["nudges"]
    ns = nudge_summary(nud)
    sent = [x for x in sigs if x.decision == "enviada"]

    st.markdown(f"### Usuario {who} · recorrido del mes")
    st.caption(
        "Todas las variables que leen las reglas, en un eje. Cada serie va como "
        "porcentaje de su propio máximo del periodo, que es lo que permite "
        "compararlas sin recurrir a dos escalas: lo que se lee es la forma y la "
        "coincidencia en el tiempo, y el valor real con su unidad está en el "
        "tooltip. **Haz clic en la leyenda** para encender o apagar cualquier "
        "serie. Debajo del cero, el carril con lo que el teléfono emitió cada "
        "día. La línea blanca es el día seleccionado."
    )

    replay = U[who]["replay"]
    by_day = {r["day"]: r for r in replay}
    days_list = [r["day"] for r in replay]
    default_day = next((r["day"] for r in replay if r["alert"]), days_list[-1])

    cursor = st.select_slider(
        "Día del periodo", options=days_list, value=default_day,
        format_func=fecha, key=f"cursor_{who}")
    st_now = by_day[cursor]

    nudge_days = {r["day"] for r in replay if r["nudge"] and r["nudge"].fired}
    alert_days, positive_days = {}, {}
    for r in replay:
        if r["alert"]:
            alert_days[r["day"]] = "enviada"
        elif r["digest_entry"]:
            alert_days[r["day"]] = "resumen"
        if r["positives"]:
            positive_days[r["day"]] = True

    st.plotly_chart(
        charts.tracked_series(F[who], who, cursor, nudge_days, alert_days,
                              positive_days),
        width="stretch", key=f"k_tracked_{who}")

    st.markdown(f"#### Salidas del {fecha(cursor)}")
    row = F[who].set_index("day").loc[cursor]
    n = st_now["nudge"]
    pos_user = [x for x in st_now["positives"] if x.audience == "usuario"]
    pos_guard = [x for x in st_now["positives"] if x.audience == "tutor"]

    cols = st.columns(3 if HAS_GUARDIAN[who] else 2)

    with cols[0]:
        st.markdown('<div class="eyebrow">Pantalla del usuario</div>',
                    unsafe_allow_html=True)
        if pos_user:
            x = pos_user[0]
            st.markdown(theme.phone(
                "09:00", "BALANCE",
                f"<div class='phone-eyebrow'>Tu resumen</div>"
                f"<div class='phone-h'>{x.headline}</div>"
                f"<div class='phone-p'>{x.guardian_text}</div>"
                + "".join(f"<div class='phone-row'><span>{k}</span>"
                          f"<span>{v}</span></div>"
                          for k, v in x.evidence.items())
                + "<div class='phone-cta ghost'>Ver la semana</div>"),
                unsafe_allow_html=True)
        elif n and n.fired:
            st.markdown(theme.phone(
                pd.Timestamp(n.at_ms, unit="ms").strftime("%H:%M"), "BALANCE",
                f"<div class='phone-eyebrow'>Nudge nocturno</div>"
                f"<div class='phone-h'>Es la {n.reopens}ª vez que abres el "
                f"teléfono esta noche.</div>"
                f"<div class='phone-p'>Hace un mes, a esta hora ya lo habías "
                f"soltado.</div>"
                f"<div class='phone-cta'>Apagar hasta mañana</div>"
                f"<div class='phone-cta ghost'>5 minutos más</div>"),
                unsafe_allow_html=True)
        else:
            empty_box("Sin notificaciones")

    if HAS_GUARDIAN[who]:
        with cols[1]:
            st.markdown('<div class="eyebrow">Teléfono del tutor</div>',
                        unsafe_allow_html=True)
            g = st_now["alert"] or (pos_guard[0] if pos_guard else None)
            if g is not None:
                st.markdown(theme.phone(
                    "09:12", f"BALANCE · TUTOR DE {who}",
                    f"<div class='phone-eyebrow'>"
                    f"{'Aviso' if g.tone == 'aviso' else 'Resumen'}</div>"
                    f"<div class='phone-h'>{g.headline}</div>"
                    f"<div class='phone-p'>{g.guardian_text}</div>"
                    f"<div class='phone-cta ghost'>Ver resumen semanal</div>"),
                    unsafe_allow_html=True)
            else:
                empty_box("Sin notificaciones")

    with cols[-1]:
        st.markdown('<div class="eyebrow">Guardado en el dispositivo</div>',
                    unsafe_allow_html=True)
        st.markdown(
            f"<div class='phone-row'><span>Pantalla</span>"
            f"<span>{row.screen_min:.0f} min</span></div>"
            f"<div class='phone-row'><span>Desbloqueos</span>"
            f"<span>{row.pickups:.0f}</span></div>"
            f"<div class='phone-row'><span>Madrugada</span>"
            f"<span>{row.night_min:.0f} min</span></div>"
            f"<div class='phone-row'><span>Última pantalla nocturna</span>"
            f"<span>{reloj(row.night_end_h)}</span></div>"
            f"<div class='phone-row'><span>Desconexión más larga</span>"
            f"<span>{row.longest_offline_h:.1f} h</span></div>"
            f"<div class='phone-row'><span>· empezó</span>"
            f"<span>{row.longest_offline_when or 'sin racha'}</span></div>"
            f"<div class='phone-row'><span>Cuota de distracción</span>"
            f"<span>{row.distract_share*100:.0f} %</span></div>"
            f"<div class='phone-row'><span>Intentos sensibles</span>"
            f"<span>{row.blocks_sensitive:.0f}</span></div>"
            f"<div class='phone-row'><span>Bloqueos totales</span>"
            f"<span>{row.blocks:.0f}</span></div>"
            f"<div class='phone-row'><span>Índice del día</span>"
            f"<span>{row.score:.0f} / 100</span></div>"
            f"<div class='phone-row'><span>Nudges hasta hoy</span>"
            f"<span>{st_now['nudges_so_far']}</span></div>"
            f"<div class='phone-row'><span>Refuerzos hasta hoy</span>"
            f"<span>{st_now['positives_so_far']}</span></div>",
            unsafe_allow_html=True)
        st.caption(
            "Estas cifras se calculan y se almacenan en el teléfono."
            + ("  Al tutor sólo llega el agregado redondeado del resumen "
               "semanal." if HAS_GUARDIAN[who] else "")
        )

    st.markdown(f"### Todo lo que emitió el teléfono en el mes")
    em = U[who]["emissions"]
    if em:
        st.dataframe(pd.DataFrame([{
            "Fecha": fecha(e["day"]),
            "Destino": e["destino"],
            "Tipo": e["tipo"],
            "Detalle": e["detalle"],
        # altura al contenido: una tabla de 3 filas con hueco para 10 parece
        # que ha fallado la carga.
        } for e in em]), width="stretch", hide_index=True,
            height=min(320, 38 + 35 * len(em)))
        st.caption(
            f"{len(em)} salidas en 30 días: "
            f"{sum(1 for e in em if e['destino'].startswith('Usuario'))} al "
            f"usuario, "
            f"{sum(1 for e in em if e['destino'] == 'Tutor · notificación')} "
            f"como notificación al tutor y "
            f"{sum(1 for e in em if e['destino'] == 'Tutor · resumen semanal')} "
            f"como entrada de resumen semanal."
        )
    else:
        st.caption("El teléfono no emitió nada en el periodo.")

    st.markdown(f"### Usuario {who} · notificaciones del periodo")
    kpis([
        ("Notificaciones al tutor",
         f"{len(sent)}" if HAS_GUARDIAN[who] else "n/a",
         f"cupo {ALERT_BUDGET}/mes" if HAS_GUARDIAN[who] else "perfil sin tutor"),
        ("En resumen semanal",
         f"{sum(1 for x in sigs if x.decision == 'resumen')}"
         if HAS_GUARDIAN[who] else "n/a", "sin notificación"),
        ("Refuerzos enviados",
         f"{sum(1 for x in U[who]['positives'] if x.decision == 'enviada')}",
         "uno por semana como máximo"),
        ("Noches con nudge", f"{ns['noches con aviso']}/{ns['noches']}",
         f"{ns['tasa de aparición']*100:.0f} % de las noches"),
        ("Min tras el nudge", f"{ns['min en juego tras el aviso']:.0f}",
         f"{ns['cuota del total nocturno']*100:.0f} % del total nocturno"),
    ])

    st.markdown("### Notificaciones enviadas al tutor")
    if not HAS_GUARDIAN[who]:
        note(
            f"<b>Perfil sin tutor asignado.</b> El usuario {who} es un adulto: no "
            f"hay destinatario al que notificar, así que las reglas de aviso "
            f"corren igual pero su salida sólo alimenta el índice y los nudges en "
            f"el propio dispositivo.<br><br>"
            f"En el periodo no se ha activado ninguna de las tres reglas: "
            f"{d.night_min.sum():.0f} minutos de pantalla nocturna en 30 días y "
            f"{ns['noches con aviso']} noches con nudge.",
            "good")
    elif not sent:
        note(
            f"<b>Ninguna en el periodo.</b> El usuario {who} no ha activado "
            f"ninguna regla: {d.night_min.sum():.0f} minutos de pantalla nocturna "
            f"en 30 días y {ns['noches con aviso']} noches con nudge. El tutor "
            f"recibe únicamente el resumen semanal en estado «todo en orden».",
            "good")
    for x in sent:
        ev = "".join(f"<div class='phone-row'><span>{k}</span>"
                     f"<span>{v}</span></div>" for k, v in x.evidence.items())
        st.markdown(
            f'<div class="eyebrow">Notificación · {fecha(x.day)} · '
            f'destinatario: tutor del usuario {who}</div>',
            unsafe_allow_html=True)
        _pc, _pr = st.columns([1, 2])
        with _pc:
            st.markdown(theme.phone(
                "09:12", f"BALANCE · TUTOR DE {who}",
                f"<div class='phone-eyebrow'>Aviso</div>"
                f"<div class='phone-h'>{x.headline}</div>"
                f"<div class='phone-p'>{x.guardian_text}</div>"
                f"<div class='phone-cta ghost'>Ver resumen semanal</div>"),
                unsafe_allow_html=True)
        note(
            f"<b>Regla:</b> <code>{x.key}</code> · "
            f"activa del {fecha(x.day)} al {fecha(x.until)} "
            f"({x.days_true} días) · prioridad {x.priority:.2f}.<br><br>"
            f"La regla deja de cumplirse el {fecha(x.until)} porque la referencia "
            f"móvil de 14 días incorpora el comportamiento nuevo. El aviso se "
            f"emite una vez, al detectar el cambio. El nivel absoluto sigue "
            f"reflejado en el índice y en el resumen semanal, que no usan "
            f"referencia móvil.",
            "serious")
        with st.expander("Datos que respaldan el aviso (no salen del dispositivo)"):
            st.markdown(ev, unsafe_allow_html=True)
            st.caption(
                "El tutor recibe el texto de la notificación. Estas cifras se "
                "calculan y se quedan en el teléfono.")

    st.markdown("### Refuerzos enviados al usuario")
    pos = U[who]["positives"]
    pos_sent = [x for x in pos if x.decision == "enviada"]
    if pos_sent:
        for x in pos_sent:
            st.markdown(
                f'<div class="eyebrow">{fecha(x.day)} · destinatario: '
                f'{"el propio usuario" if x.audience == "usuario" else f"tutor del usuario {who}"}'
                f'</div>', unsafe_allow_html=True)
            note(f"<b>{x.headline}</b><br>«{x.guardian_text}»", "good")
    else:
        st.caption("Ningún refuerzo en el periodo.")
    pos_held = [x for x in pos if x.decision != "enviada"]
    if pos_held:
        with st.expander(f"{len(pos_held)} refuerzos registrados sin notificar"):
            st.dataframe(pd.DataFrame([{
                "Fecha": fecha(x.day), "Regla": x.key,
                "Destinatario": x.audience,
                "Detalle": x.guardian_text, "Motivo": x.reason,
            } for x in pos_held]), width="stretch", hide_index=True)

    st.markdown("### Señales retenidas")
    rest = [x for x in sigs if x.decision != "enviada"]
    if rest:
        st.dataframe(pd.DataFrame([{
            "Regla": x.key,
            "Detectada": fecha(x.day),
            "Prioridad": x.priority,
            "Destino": x.decision,
            "Motivo": x.reason,
        } for x in rest]), width="stretch", hide_index=True)
    else:
        st.caption("Ninguna señal retenida en el periodo.")

    st.markdown("### Cobertura de las reglas")
    rows = []
    for key, desc in [
        ("night_drift", "Mediana de 5 noches contra las 14 anteriores, más "
                        "retraso de la hora de última pantalla"),
        ("sensitive_spike", "Intentos ADULT o GAMBLING de 7 días contra el "
                            "ritmo de los 7 anteriores"),
        ("screen_jump", "Mediana de tiempo de pantalla de 5 días contra las 14 "
                        "anteriores"),
    ]:
        hit = next((x for x in sigs if x.key == key), None)
        rows.append({
            "Regla": key,
            "Qué compara": desc,
            "Usuario A": next((f"{x.decision} · {fecha(x.day)}"
                               for x in U["A"]["alerts"] if x.key == key),
                              "no se activa"),
            "Usuario B": next((f"{x.decision} · {fecha(x.day)}"
                               for x in U["B"]["alerts"] if x.key == key),
                              "no se activa"),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    note(
        f"<code>screen_jump</code> no se activa en ninguno de los dos perfiles. "
        f"El uso diario del usuario B crece un "
        f"{(wk(F['B'],'screen_min',4)/wk(F['B'],'screen_min',1)-1)*100:.0f} % en "
        f"el mes, por debajo del umbral de cualquier regla de volumen razonable, "
        f"mientras su franja nocturna se multiplica por "
        f"{wk(F['B'],'night_min',4)/max(wk(F['B'],'night_min',1),.01):.0f}. La "
        f"detección de este caso depende de vigilar el horario, no el total.",
        "warn")

    st.markdown("### Nudge en dispositivo")
    st.caption(
        f"Se muestra en la segunda reapertura a partir de las "
        f"{int(23 + NUDGE_AFTER_MIN // 60):02d}:{NUDGE_AFTER_MIN % 60:02d}, una "
        f"vez por noche como máximo. Cifras obtenidas reproduciendo la regla "
        f"sobre los 30 días del periodo."
    )
    ca, cb = st.columns(2)
    with ca:
        st.markdown(f"**Usuario {who} · activación**")
        st.markdown(
            f"<div class='phone-row'><span>Noches evaluadas</span>"
            f"<span>{ns['noches']}</span></div>"
            f"<div class='phone-row'><span>Noches con aviso</span>"
            f"<span>{ns['noches con aviso']} "
            f"({ns['tasa de aparición']*100:.0f} %)</span></div>"
            f"<div class='phone-row'><span>Min nocturnos del mes</span>"
            f"<span>{ns['min nocturnos totales']:.0f}</span></div>"
            f"<div class='phone-row'><span>Min posteriores al aviso</span>"
            f"<span>{ns['min en juego tras el aviso']:.0f} "
            f"({ns['cuota del total nocturno']*100:.0f} %)</span></div>"
            f"<div class='phone-row'><span>Por noche con aviso</span>"
            f"<span>{ns['min en juego por noche con aviso']:.0f} min</span></div>",
            unsafe_allow_html=True)
    with cb:
        quiet = Counter(n.quiet_reason for n in nud if n.quiet_reason)
        st.markdown("**Noches sin aviso · motivo**")
        for reason, n in quiet.most_common():
            st.markdown(
                f"<div class='phone-row'><span>{reason}</span>"
                f"<span>{n}</span></div>", unsafe_allow_html=True)

    note(
        f"Los minutos posteriores al aviso acotan el margen del nudge: "
        f"{nudge_summary(U['B']['nudges'])['min en juego tras el aviso']:.0f} de "
        f"los {nudge_summary(U['B']['nudges'])['min nocturnos totales']:.0f} "
        f"minutos nocturnos del usuario B "
        f"({nudge_summary(U['B']['nudges'])['cuota del total nocturno']*100:.0f} "
        f"%), unos {nudge_summary(U['B']['nudges'])['min en juego por noche con aviso']:.0f} "
        f"por noche en que aparece. Es el máximo teórico recuperable, no el "
        f"efecto esperado.<br><br>"
        f"La tasa de activación en el usuario A es del 0 %: la regla no se "
        f"dispara ninguna de sus 30 noches sin necesidad de configuración "
        f"específica por perfil."
    )

# ===========================================================================
# 8 · LOS DATOS
# ===========================================================================
with TABS[7]:
    st.markdown("### Qué hay exactamente en los ficheros")

    ev = pd.DataFrame([
        {"Usuario": u, **Counter(e["event_type"] for e in U[u]["events"])}
        for u in DATA]).set_index("Usuario").T.fillna(0).astype(int)
    ev["Qué significa"] = [{
        "SCREEN_ON": "La pantalla se enciende. Puede ser un vistazo o el inicio de un uso real.",
        "SCREEN_OFF": "La pantalla se apaga.",
        "USER_PRESENT": "Desbloqueo real (PIN / biometría). Es lo que convierte un SCREEN_ON en pickup.",
        "APP_FOREGROUND": "Una app pasa a primer plano. Trae package_name y category.",
        "URL_VISIT": "Página vista en el navegador. Trae url_domain y category. Sólo dominio, nunca ruta.",
        "BLOCK": "Un intento detenido. El contenido NO llegó a abrirse. Trae block_type.",
    }[i] for i in ev.index]
    st.dataframe(ev, width="stretch")

    st.markdown("### Campos del evento")
    st.dataframe(pd.DataFrame([
        ("id", "int", "Monotónico por fichero, en orden temporal.",
         "Sólo desempate al ordenar."),
        ("event_type", "str", "Uno de los seis tipos de arriba.",
         "Máquina de estados de pantalla, atribución de tiempo, bloqueos."),
        ("timestamp_millis", "int", "Epoch en milisegundos, reloj de pared en UTC.",
         "Todo. Día = medianoche local; la noche se mide 23:00→06:00 del día siguiente."),
        ("package_name", "str|null", "Paquete Android. En APP_FOREGROUND y en BLOCK de app.",
         "Ranking de apps, cambios de app, apps distintas."),
        ("url_domain", "str|null", "Sólo dominio. En URL_VISIT y en BLOCK de sitio.",
         "Ranking de dominios. El tiempo de navegador se reasigna al dominio."),
        ("category", "str|null", "Vocabulario común para apps y sitios.",
         "Minutos por categoría, cuota de distracción, sensibles (ADULT/GAMBLING)."),
        ("block_type", "str|null", "APP · URL · NUDITY. Sólo en BLOCK.",
         "Separa el filtro de listas de la detección de desnudos en dispositivo."),
        ("is_keyguard_locked", "bool|null", "true en SCREEN_ON pasivo, false en USER_PRESENT.",
         "Distingue vistazo de pickup real."),
    ], columns=["Campo", "Tipo", "Qué es", "Para qué lo usamos"]),
        width="stretch", hide_index=True)

    st.markdown("### Anomalías del stream y tratamiento aplicado")
    note(
        "<b>1 · Sesiones de pantalla solapadas.</b> 77 <code>SCREEN_ON</code> en "
        "el usuario A y 411 en el B ocurren con la pantalla ya encendida, "
        "compensados más tarde por <code>SCREEN_OFF</code> consecutivos. El dato "
        "no dice qué apagado cierra qué encendido, y elegir mal cambia el "
        "resultado en las dos direcciones: emparejando en pila salen 64,9 h en "
        "el usuario A (+6 %, el solape se cuenta dos veces) y en cola 56,7 h "
        "(−7 %, se pierde el tramo sobrante).<br>"
        "La pantalla se modela como <b>contador de profundidad</b> (ON suma, OFF "
        "resta; encendida mientras &gt; 0), que devuelve la <b>unión</b> de los "
        "tramos: <b>61,1 h</b>. La unión no depende del emparejamiento elegido, "
        "y es lo que significa «la pantalla estuvo encendida»."
        "<br><br>"
        "<b>2 · Días truncados por el borde del fichero.</b> El fichero del "
        "usuario B termina a las 00:46 del 31 de mayo. Ese día tiene 0,8 h de "
        "cobertura y queda excluido de medias, rankings, mapa de calor y "
        "bloqueos; sus eventos sí computan en la noche del día 30. Sin ese "
        "filtro la media de pantalla del usuario B baja de 261,8 a 253,7 min."
        "<br><br>"
        "<b>3 · Primer desbloqueo con suelo a las 06:00.</b> Con el corte de día "
        "a medianoche, un día que arranca a las 00:20 (cola de la noche anterior) "
        "se registraría como inicio de jornada. El primer desbloqueo se define "
        "como el primero a partir de las 06:00; la madrugada se contabiliza "
        "aparte."
        "<br><br>"
        "<b>4 · Tramos que cruzan medianoche.</b> Se parten en el corte de día "
        "para que el tiempo de pantalla diario sume exactamente el día."
        "<br><br>"
        "<b>5 · Guardas que no llegan a activarse aquí.</b> Eventos de app o URL "
        "con la pantalla apagada, <code>USER_PRESENT</code> sin "
        "<code>SCREEN_ON</code> previo y apps en primer plano más de 45 minutos "
        "están contemplados en el código y no ocurren en estos dos ficheros. La "
        "única anomalía que sí aparece son 4 <code>USER_PRESENT</code> "
        "duplicados dentro de un mismo tramo en el usuario A y 6 en el B, que "
        "quedan registrados en vez de descartarse en silencio."
    )

    st.markdown("### De evento a métrica")
    st.dataframe(pd.DataFrame([
        ("Tiempo de pantalla", "Unión de intervalos SCREEN_ON→SCREEN_OFF, partida a medianoche."),
        ("Pickup real", "SCREEN_ON con un USER_PRESENT antes del siguiente ON/OFF."),
        ("Vistazo", "SCREEN_ON sin USER_PRESENT: la pantalla se encendió, el teléfono no se abrió."),
        ("Tiempo por app", "De APP_FOREGROUND al siguiente cambio de foreground, BLOCK o apagado. Tope 45 min."),
        ("Tiempo por dominio", "Igual, pero URL_VISIT le quita el tiempo al navegador y se lo queda el dominio."),
        ("Franja nocturna", "23:00 del día D → 06:00 del día D+1. El día natural corta a medianoche; el sueño no."),
        ("Desconexión más larga", "Mayor hueco sin pantalla dentro de la vigilia (07:00–23:00)."),
        ("Cambio de app", "Transición real de foreground entre paquetes distintos."),
        ("Cuota de distracción", "Minutos en SOCIAL_MEDIA + ENTERTAINMENT + GAMING sobre el tiempo atribuido."),
        ("Tu normal", "Mediana móvil de los 14 días anteriores del propio usuario (mediana, no media: un día raro no debe mover el listón)."),
    ], columns=["Métrica", "Cómo se deriva"]), width="stretch", hide_index=True)

    st.markdown("### Cobertura de la atribución")
    kpis([(f"{u} · pantalla reconstruida", f"{U[u]['screen_h']:.0f} h", None)
          for u in DATA] +
         [(f"{u} · atribuido a app/sitio",
           f"{U[u]['attributed_h']/U[u]['screen_h']*100:.0f} %", None) for u in DATA])
    st.caption(
        "El resto es pantalla encendida sin app en primer plano: pantalla de "
        "bloqueo, escritorio y notificaciones. El 67 % del usuario B frente al "
        "86 % del A es consistente con su patrón de encendidos frecuentes que no "
        "llegan a abrir contenido."
    )

    st.markdown("### El índice, componente a componente")
    st.dataframe(pd.DataFrame([
        (label, f"{good:g}", f"{bad:g}", f"{w*100:.0f} %")
        for col, label, good, bad, w in COMPONENTS],
        columns=["Componente", "Valor que da 100", "Valor que da 0", "Peso"]),
        width="stretch", hide_index=True)
    c1, c2 = st.columns(2)
    for col, u in ((c1, "A"), (c2, "B")):
        mean_row = F[u].mean(numeric_only=True)
        col.plotly_chart(charts.score_breakdown(contributions(mean_row), u),
                         width="stretch", key=f"k_breakdown_{u}")
    note(
        "Los bloqueos no puntúan en el índice. Un <code>BLOCK</code> indica que "
        "el filtro actuó y el contenido no se abrió; descontar puntos por el "
        "intento penalizaría al usuario por algo que el producto ya ha resuelto "
        "e incentivaría desactivar la protección. Los bloqueos alimentan las "
        "reglas de aviso y el resumen del tutor, no la puntuación."
    )
