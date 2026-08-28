"""
Capa 3 · figuras. Ninguna decide nada: reciben frames ya calculados.

Reglas que se respetan en todas (skill `dataviz`):
* nunca dos ejes Y: dos magnitudes distintas son dos gráficos;
* el color sigue a la entidad (usuario, categoría), nunca a su posición;
* con ≥2 series siempre hay leyenda, y con ≤4 además etiqueta directa;
* separación de 2 px entre rellenos apilados (`marker_line` del color del panel);
* rejilla y ejes recesivos, marcas finas.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .theme import (
    CARD, CATEGORICAL, CATEGORY_COLOR, GOOD, INK, INK_2, MONO, MUTED, RULE,
    SERIOUS, USER_COLOR, WARN,
)

DOW_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]


def _direct_label(fig, x, y, text, color, dx=6):
    fig.add_annotation(x=x, y=y, text=f" {text}", showarrow=False,
                       xanchor="left", yanchor="middle", xshift=dx,
                       font=dict(family=MONO, size=11, color=color))


def _frame(fig, h=340, legend=True, **kw):
    fig.update_layout(height=h, showlegend=legend, **kw)
    return fig


# ---------------------------------------------------------------------------
# Series temporales
# ---------------------------------------------------------------------------

def compare_line(frames: dict[str, pd.DataFrame], col: str, title: str,
                 unit: str = "", smooth: int = 7, h: int = 340) -> go.Figure:
    """Una línea suavizada por usuario + el dato crudo en sombra.

    El suavizado (mediana móvil de 7 días) es lo que se lee; el punto diario
    queda detrás en baja opacidad para no esconder la varianza real.
    """
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        fig.add_trace(go.Scatter(
            x=df["day"], y=df[col], mode="markers",
            marker=dict(size=4, color=c, opacity=.28),
            name=f"{user} · diario", legendgroup=user, showlegend=False,
            hovertemplate="%{y:.0f} " + unit + "<extra>Usuario " + user + "</extra>",
        ))
        sm = df[col].rolling(smooth, min_periods=2, center=True).mean()
        fig.add_trace(go.Scatter(
            x=df["day"], y=sm, mode="lines", line=dict(color=c, width=2.4),
            name=f"Usuario {user}", legendgroup=user,
            hovertemplate="%{y:.0f} " + unit + " (media " + str(smooth) + "d)"
                          "<extra>Usuario " + user + "</extra>",
        ))
        _direct_label(fig, df["day"].iloc[-1], sm.iloc[-1], user, c)
    fig.update_layout(title=title, yaxis_title=unit)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def daily_bars_vs_baseline(df: pd.DataFrame, col: str, baseline: str,
                           title: str, unit: str, user: str,
                           h: int = 320) -> go.Figure:
    """Barra diaria contra la mediana móvil personal de 14 días.

    Es la forma de que un número signifique algo: no "2 h de pantalla", sino
    "2 h, media hora menos de lo normal en ti".
    """
    c = USER_COLOR[user]
    over = (df[col] > df[baseline]).fillna(False)

    # Dos trazas en vez de una con colores mezclados: así el ámbar entra en la
    # leyenda y se explica solo, sin que haya que leer el pie de foto.
    fig = go.Figure()
    for mask, name, color in (
        (~over, "Igual o por debajo de tu normal", c),
        (over, "Por encima de tu normal", WARN),
    ):
        fig.add_trace(go.Bar(
            x=df["day"][mask], y=df[col][mask], name=name,
            marker=dict(color=color, line=dict(color=CARD, width=1.5)),
            hovertemplate="%{x|%a %d %b}<br>%{y:.0f} " + unit + "<extra></extra>",
        ))
    fig.add_trace(go.Scatter(
        x=df["day"], y=df[baseline], mode="lines",
        line=dict(color=INK, width=1.6, dash="dot"),
        name="Tu normal (mediana de 14 días)",
        hovertemplate="normal: %{y:.0f} " + unit + "<extra></extra>",
    ))
    fig.update_layout(title=title, yaxis_title=unit, bargap=.25,
                      barmode="overlay", margin=dict(t=48, r=24, b=86, l=56),
                      legend=dict(y=-0.22))
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h + 20)


def day_span(df: pd.DataFrame, user: str, h: int = 340) -> go.Figure:
    """De la primera desbloqueada a la última pantalla apagada, día a día.

    El eje empieza a las 04:00 para que la madrugada quede *arriba* (24–28) en
    vez de saltar al suelo del gráfico. La barra es la jornada con teléfono;
    lo que sobra por arriba es lo que se está comiendo a la noche.
    """
    c = USER_COLOR[user]
    start = df["first_pickup_h"]
    end = df["last_use_h"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["day"], y=(end - start), base=start,
        marker=dict(color=c, opacity=.55, line=dict(color=CARD, width=1.2)),
        name="Jornada con teléfono",
        customdata=list(zip(df["first_pickup_clock"], df["last_use_clock"])),
        hovertemplate="%{x|%a %d %b}<br>de %{customdata[0]} a %{customdata[1]}"
                      "<extra></extra>",
    ))
    fig.add_hline(y=23, line=dict(color=WARN, width=1.2, dash="dot"),
                  annotation_text="23:00",
                  annotation_position="right",
                  annotation_font=dict(family=MONO, size=10, color=WARN))
    fig.add_trace(go.Scatter(
        x=df["day"], y=end.rolling(7, min_periods=2, center=True).mean(),
        mode="lines", line=dict(color=INK, width=2),
        name="Última pantalla (media de 7 días)", hoverinfo="skip",
    ))
    lo = max(5, int(start.min()) - 1)
    hi = min(29, int(end.max()) + 2)
    ticks = list(range(lo + lo % 2, hi + 1, 2))
    fig.update_layout(title=f"Usuario {user} · de qué hora a qué hora",
                      yaxis_title="hora local")
    fig.update_yaxes(tickvals=ticks,
                     ticktext=[f"{t % 24:02d}:00" for t in ticks], range=[lo, hi])
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def night_drift(frames: dict[str, pd.DataFrame], h: int = 340) -> go.Figure:
    """Minutos de pantalla entre las 23:00 y las 06:00, por noche."""
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        # Una serie plana en cero se lee como "falta el dato" si no se dice, y
        # la aclaración va en la leyenda, no en una anotación: sobre las barras
        # tapaba lo que hay que leer, y encima del título chocaba con él.
        flat = df["night_min"].max() < 0.5
        label = (f"Usuario {user}: 0 min las {len(df)} noches" if flat
                 else f"Usuario {user}")
        fig.add_trace(go.Bar(
            x=df["day"], y=df["night_min"], name=label,
            marker=dict(color=c, line=dict(color=CARD, width=1.2)),
            hovertemplate="%{x|%a %d %b}<br>%{y:.0f} min de madrugada"
                          "<extra>Usuario " + user + "</extra>",
        ))
    fig.update_layout(title="Pantalla en franja nocturna (23:00 a 06:00)",
                      yaxis_title="minutos", barmode="group", bargap=.2)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Composición
# ---------------------------------------------------------------------------

def category_area(cat_daily: pd.DataFrame, title: str, h: int = 360) -> go.Figure:
    """Minutos por categoría y día, apilados. Orden fijo, nunca por ranking."""
    order = [c for c in CATEGORY_COLOR if c in set(cat_daily["category"])]
    wide = (cat_daily.pivot_table(index="day", columns="category",
                                  values="minutes", aggfunc="sum")
            .reindex(columns=order).fillna(0))
    roll = wide.rolling(3, min_periods=1, center=True).mean()
    fig = go.Figure()
    for cat in order:
        fig.add_trace(go.Scatter(
            x=roll.index, y=roll[cat], mode="lines", stackgroup="one",
            name=cat.replace("_", " ").title(),
            line=dict(width=1.2, color=CARD),
            fillcolor=CATEGORY_COLOR[cat],
            hovertemplate="%{y:.0f} min<extra>" + cat + "</extra>",
        ))
    fig.update_layout(title=title, yaxis_title="minutos (media móvil 3 d)")
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def top_bars(tot: pd.DataFrame, title: str, n: int = 10,
             h: int = 380) -> go.Figure:
    """Ranking horizontal por minutos, coloreado por categoría."""
    d = tot.head(n).iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["minutes"], y=d["label"], orientation="h",
        marker=dict(color=[CATEGORY_COLOR.get(c, MUTED) for c in d["category"]],
                    line=dict(color=CARD, width=1.5)),
        text=[f"{m:,.0f} min" for m in d["minutes"]],
        textposition="outside",
        textfont=dict(family=MONO, size=11, color=INK_2),
        customdata=d[["opens", "min_per_open", "category"]].values,
        hovertemplate="<b>%{y}</b><br>%{x:.0f} min totales<br>"
                      "%{customdata[0]} aperturas · %{customdata[1]:.1f} min por apertura"
                      "<br>%{customdata[2]}<extra></extra>",
    ))
    fig.update_layout(title=title, xaxis_title="minutos del mes", bargap=.28,
                      margin=dict(t=48, r=48, b=56, l=110))
    fig.update_xaxes(range=[0, d["minutes"].max() * 1.24])
    fig.update_yaxes(tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h, legend=False)


def hour_heat(hh: pd.DataFrame, user: str, h: int = 330) -> go.Figure:
    """Reloj semanal: minutos de pantalla por día de la semana y hora."""
    grid = (hh.pivot_table(index="dow", columns="hour", values="minutes",
                           aggfunc="sum")
            .reindex(index=range(7), columns=range(24)).fillna(0))
    fig = go.Figure(go.Heatmap(
        z=grid.values, x=list(range(24)), y=DOW_ES,
        colorscale=[[0, "#131317"], [.2, "#17324f"], [.45, "#1f5ca3"],
                    [.75, "#3d86d8"], [1, "#7fb6f2"]],
        xgap=2, ygap=2,
        colorbar=dict(title=dict(text="min", font=dict(family=MONO, size=10,
                                                      color=INK_2)),
                      tickfont=dict(family=MONO, size=10, color=INK_2),
                      outlinewidth=0, thickness=9, len=.8, x=1.02),
        hovertemplate="%{y} · %{x}:00<br>%{z:.0f} min<extra></extra>",
    ))
    fig.update_layout(title=f"Usuario {user} · reloj semanal de pantalla",
                      xaxis_title="hora local")
    fig.update_xaxes(dtick=2, showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed",
                     tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h, legend=False, hovermode="closest")


# ---------------------------------------------------------------------------
# Bloqueos
# ---------------------------------------------------------------------------

def blocks_daily(bf: pd.DataFrame, title: str, h: int = 340) -> go.Figure:
    """Intentos bloqueados por día, apilados por categoría."""
    order = [c for c in CATEGORY_COLOR if c in set(bf["category"])]
    wide = (bf.pivot_table(index="day", columns="category", values="target",
                           aggfunc="count").reindex(columns=order).fillna(0))
    fig = go.Figure()
    for cat in order:
        fig.add_trace(go.Bar(
            x=wide.index, y=wide[cat], name=cat.replace("_", " ").title(),
            marker=dict(color=CATEGORY_COLOR[cat],
                        line=dict(color=CARD, width=1.2)),
            hovertemplate="%{y:.0f}<extra>" + cat + "</extra>",
        ))
    fig.update_layout(title=title, yaxis_title="intentos bloqueados",
                      barmode="stack", bargap=.2)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def blocks_by_hour(bf: pd.DataFrame, title: str, h: int = 300) -> go.Figure:
    """A qué hora se choca contra el muro; sensibles frente al resto."""
    sens = bf[bf["category"].isin(["ADULT", "GAMBLING"])]
    rest = bf[~bf["category"].isin(["ADULT", "GAMBLING"])]
    fig = go.Figure()
    for name, d, color in (("Distracción ordinaria", rest, "#3987e5"),
                           ("Adulto / apuestas", sens, "#e66767")):
        counts = d.groupby("hour").size().reindex(range(24)).fillna(0)
        fig.add_trace(go.Bar(
            x=list(range(24)), y=counts.values, name=name,
            marker=dict(color=color, line=dict(color=CARD, width=1.2)),
            hovertemplate="%{x}:00 → %{y:.0f}<extra>" + name + "</extra>",
        ))
    fig.update_layout(title=title, xaxis_title="hora local",
                      yaxis_title="intentos del mes", barmode="stack", bargap=.15,
                      margin=dict(t=48, r=24, b=96, l=56),
                      legend=dict(y=-0.3))
    fig.update_xaxes(dtick=2)
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def score_line(frames: dict[str, pd.DataFrame], h: int = 340) -> go.Figure:
    fig = go.Figure()
    for user, df in frames.items():
        c = USER_COLOR[user]
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["score"], mode="markers",
            marker=dict(size=4, color=c, opacity=.3),
            name=f"{user} diario", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(
            x=df["day"], y=df["score_7d"], mode="lines",
            line=dict(color=c, width=2.6), name=f"Usuario {user}",
            hovertemplate="%{y:.0f}/100<extra>Usuario " + user + "</extra>"))
        _direct_label(fig, df["day"].iloc[-1], df["score_7d"].iloc[-1], user, c)
    fig.update_layout(title="Índice de bienestar digital (media 7 días)",
                      yaxis_title="0 – 100")
    fig.update_yaxes(range=[0, 100], dtick=20)
    fig.update_xaxes(tickformat="%d %b")
    return _frame(fig, h)


def score_breakdown(contrib: pd.DataFrame, user: str, h: int = 300) -> go.Figure:
    """Cuántos puntos aporta y cuántos deja escapar cada componente."""
    d = contrib.iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["points"], y=d["component"], orientation="h", name="Puntos ganados",
        marker=dict(color=USER_COLOR[user], line=dict(color=CARD, width=1.5)),
        hovertemplate="%{x:.1f} de %{customdata:.0f} posibles<extra></extra>",
        customdata=d["weight"] * 100))
    fig.add_trace(go.Bar(
        x=d["lost"], y=d["component"], orientation="h", name="Puntos perdidos",
        marker=dict(color="#33333a", line=dict(color=CARD, width=1.5)),
        hovertemplate="%{x:.1f} perdidos<extra></extra>"))
    fig.update_layout(title=f"Usuario {user} · de dónde sale el índice (media del mes)",
                      barmode="stack", bargap=.3, xaxis_title="puntos sobre 100")
    fig.update_yaxes(tickfont=dict(family=MONO, size=11, color=INK))
    return _frame(fig, h)


# ---------------------------------------------------------------------------
# Recorrido del mes
# ---------------------------------------------------------------------------

#: Las variables que leen las reglas, con la transformada que las hace
#: comparables entre sí y la regla o reglas que las consumen.
#:
#: `to_comparable` lleva cada serie a los mismos ejes sin cambiar su forma: todas
#: se expresan como porcentaje de su propio máximo del periodo. No es una escala
#: doble disfrazada; es una única escala con una transformada declarada, y el
#: valor real con su unidad viaja en el tooltip. Se divide por el máximo y no se
#: reescala a min-max porque el cero tiene que seguir siendo el cero: en el
#: usuario A, "cero minutos de madrugada" es el dato, y min-max lo pintaría a
#: media altura.
#: (columna, etiqueta, unidad, slot de color, patrón de línea, reglas)
#:
#: El patrón no es decorativo. La validación de la paleta sobre fondo oscuro
#: deja el peor par adyacente (verde ↔ amarillo) en ΔE 10,3, dentro de la banda
#: suelo para daltonismo protán, y la norma es que ahí hace falta una
#: codificación secundaria. Con siete series solapadas y sólo leyenda, el trazo
#: es esa codificación: cada serie se distingue aunque el color no llegue.
TRACKED = [
    ("night_min", "Pantalla de madrugada", "min", 0, "solid",
     "night_drift · night_streak"),
    ("night_end_min", "Última pantalla (desde 23:00)", "min", 1, "dash",
     "night_drift"),
    ("screen_min", "Pantalla al día", "min", 2, "solid", "screen_jump"),
    ("longest_offline_h", "Desconexión más larga", "h", 3, "dot",
     "offline_record"),
    ("blocks", "Bloqueos al día", "", 4, "dashdot", "calm_week"),
    ("blocks_sensitive", "Intentos sensibles", "", 5, "dash",
     "sensitive_spike · filter_calm"),
    ("distract_pct", "Cuota de distracción", "%", 6, "dot", "focus_week"),
]

#: Series visibles al abrir. El resto entra con un clic en la leyenda: siete
#: líneas a la vez no se leen, y arrancar con todas encendidas obliga al lector
#: a apagar en vez de a encender.
TRACKED_DEFAULT = {"night_min", "night_end_min", "screen_min"}

#: Altura del carril de eventos, por debajo del cero de los datos.
_RAIL = -9


def _derive_tracked(df: pd.DataFrame) -> pd.DataFrame:
    """Columnas derivadas que sólo existen para este gráfico."""
    df = df.copy()
    # La hora de última pantalla se expresa como minutos a partir de las 23:00,
    # para que el cero signifique "se apagó a la hora" y no "medianoche".
    df["night_end_min"] = (df["night_end_h"] - 23) * 60
    df["longest_offline_h"] = df["longest_offline_s"] / 3600
    df["distract_pct"] = df["distract_share"] * 100
    return df


def tracked_series(df: pd.DataFrame, user: str, cursor,
                   nudge_days: set, alert_days: dict, positive_days: dict,
                   h: int = 560):
    """Todas las variables vigiladas en un solo eje, encendibles desde la leyenda.

    Cada serie va como porcentaje de su propio máximo del periodo, que es lo que
    permite compararlas sin recurrir a dos ejes Y. Lo que se lee es la forma y la
    coincidencia temporal, no el nivel; el nivel está en el tooltip y en el
    resumen semanal.

    Debajo del cero hay un carril de eventos con lo que el teléfono emitió cada
    día. También se enciende y se apaga desde la leyenda, y comparte el eje
    temporal con los datos que lo explican.
    """
    d = _derive_tracked(df)
    fig = go.Figure()

    for i, (col, label, unit, slot, trazo, reglas) in enumerate(TRACKED):
        serie = d[col]
        tope = serie.max()
        if pd.isna(tope) or tope <= 0:
            # Serie plana en cero: se dibuja igualmente, pegada al eje, para que
            # se vea que el dato existe y vale cero.
            norm = serie.fillna(0) * 0
            nota = " · sin actividad"
        else:
            norm = serie / tope * 100
            nota = ""
        fig.add_trace(go.Scatter(
            x=d["day"], y=norm, mode="lines+markers",
            name=f"{label}{nota}",
            # El grupo es sólo para titular la leyenda. Con
            # `groupclick="toggleitem"` cada entrada se apaga por su cuenta;
            # sin esa opción, Plotly apaga el grupo entero de un clic.
            legendgroup="datos",
            legendgrouptitle=dict(text="Variables vigiladas") if i == 0 else None,
            visible=True if col in TRACKED_DEFAULT else "legendonly",
            line=dict(color=CATEGORICAL[slot], width=2, dash=trazo),
            marker=dict(size=5, color=CATEGORICAL[slot],
                        symbol=["circle", "square", "diamond", "cross",
                                "x", "triangle-up", "pentagon"][slot]),
            customdata=serie,
            hovertemplate=("<b>" + label + "</b>: %{customdata:.1f} " + unit
                           + "<br>" + reglas + "<extra></extra>"),
        ))

    # --- carril de eventos --------------------------------------------------
    eventos = [
        ("Noche con nudge", sorted(nudge_days), "circle", WARN,
         "Nudge nocturno en el dispositivo"),
        ("Aviso al tutor",
         sorted(k for k, v in alert_days.items() if v == "enviada"),
         "triangle-up", SERIOUS, "Notificación enviada al tutor"),
        ("Entrada de resumen",
         sorted(k for k, v in alert_days.items() if v == "resumen"),
         "diamond", INK_2, "Señal retenida para el resumen semanal"),
        ("Refuerzo", sorted(positive_days), "star", GOOD,
         "Refuerzo enviado"),
    ]
    for i, (nombre, dias, simbolo, color, detalle) in enumerate(eventos):
        fig.add_trace(go.Scatter(
            x=dias, y=[_RAIL] * len(dias), mode="markers", name=nombre,
            legendgroup="eventos",
            legendgrouptitle=dict(text="Emisiones") if i == 0 else None,
            marker=dict(symbol=simbolo, size=11, color=color,
                        line=dict(color=CARD, width=1)),
            hovertemplate="%{x|%d %b}<br>" + detalle + "<extra></extra>",
            showlegend=True,
        ))

    fig.add_hline(y=0, line=dict(color=RULE, width=1))
    fig.add_vline(x=cursor, line=dict(color=INK, width=2))

    fig.update_layout(
        height=h, hovermode="x unified",
        yaxis_title="% del máximo del periodo",
        margin=dict(t=44, r=24, b=120, l=64),
        legend=dict(orientation="h", y=-0.24, x=0, xanchor="left",
                    yanchor="top", groupclick="toggleitem",
                    font=dict(family=MONO, size=11, color=INK_2),
                    grouptitlefont=dict(family=MONO, size=11, color=MUTED)),
    )
    fig.update_yaxes(range=[_RAIL - 5, 108], dtick=25,
                     tickvals=[0, 25, 50, 75, 100],
                     ticktext=["0", "25", "50", "75", "100 %"])
    fig.update_xaxes(tickformat="%d %b")
    fig.add_annotation(xref="paper", x=0, y=_RAIL, yanchor="middle",
                       xanchor="right", xshift=-8, text="eventos",
                       showarrow=False,
                       font=dict(family=MONO, size=10, color=MUTED))
    return fig


# ---------------------------------------------------------------------------
# Resumen semanal
# ---------------------------------------------------------------------------

def week_evolution(w: pd.DataFrame, col: str, label: str, unit: str,
                   user: str, sel: int, h: int = 260) -> go.Figure:
    """Una magnitud semana a semana, con la semana elegida resaltada.

    Las semanas incompletas van en hueco y con etiqueta: una semana de dos días
    promediada al lado de una de siete se lee como una caída que no existe.
    """
    c = USER_COLOR[user]
    labels = [f"S{i}" + (" *" if p else "") for i, p in zip(w.index, w["is_partial"])]
    fig = go.Figure(go.Bar(
        x=labels, y=w[col],
        marker=dict(color=[c if i == sel else "#2f2f36" for i in w.index],
                    line=dict(color=CARD, width=1.5)),
        text=[f"{v:,.0f}" if abs(v) >= 10 else f"{v:,.1f}" for v in w[col]],
        textposition="outside",
        textfont=dict(family=MONO, size=11, color=INK_2),
        hovertemplate="%{x}<br>%{y:.1f} " + unit + "<extra>" + label + "</extra>",
    ))
    fig.update_layout(title=label, yaxis_title=unit, bargap=.35,
                      height=h, showlegend=False,
                      margin=dict(t=44, r=20, b=36, l=54))
    fig.update_yaxes(range=[0, max(w[col].max() * 1.25, 0.1)])
    return fig


def week_days(df: pd.DataFrame, week: int, col: str, label: str, unit: str,
              user: str, h: int = 300) -> go.Figure:
    """Los días de la semana elegida contra la media de las semanas anteriores."""
    cur = df[df["week"] == week]
    prev = df[df["week"] < week]
    ref = prev[col].mean() if len(prev) else None

    fig = go.Figure(go.Bar(
        x=[DOW_ES[d] for d in cur["dow"]], y=cur[col],
        marker=dict(color=USER_COLOR[user], line=dict(color=CARD, width=1.5)),
        name=f"Semana {week}",
        hovertemplate="%{x}<br>%{y:.0f} " + unit + "<extra></extra>",
    ))
    if ref is not None:
        fig.add_hline(y=ref, line=dict(color=INK, width=1.6, dash="dot"),
                      annotation_text=f"media de semanas anteriores: {ref:,.0f}",
                      annotation_position="top left",
                      annotation_font=dict(family=MONO, size=10, color=INK_2))
    if cur[col].abs().max() == 0:
        fig.add_annotation(xref="paper", yref="paper", x=0.5, y=0.5,
                           text="Sin actividad en la semana", showarrow=False,
                           font=dict(family=MONO, size=11, color=MUTED))
        fig.update_yaxes(range=[0, 1], showticklabels=False)
    fig.update_layout(title=label, yaxis_title=unit, bargap=.3, height=h,
                      showlegend=False, margin=dict(t=52, r=20, b=40, l=54))
    return fig


def week_components(w: pd.DataFrame, sel: int, h: int = 320) -> go.Figure:
    """Los cinco componentes del índice, semana a semana.

    Es donde se ve qué parte del índice se mueve y cuál se queda quieta, que es
    la pregunta que sigue a "el índice ha bajado".
    """
    from .score import COMPONENTS
    fig = go.Figure()
    labels = [f"S{i}" for i in w.index]
    for (col, label, *_rest), color in zip(COMPONENTS, CATEGORICAL):
        fig.add_trace(go.Scatter(
            x=labels, y=w[f"score_{col}"], mode="lines+markers", name=label,
            line=dict(color=color, width=2.2), marker=dict(size=8, color=color),
            hovertemplate="%{y:.0f}/100<extra>" + label + "</extra>",
        ))
    fig.add_vline(x=f"S{sel}", line=dict(color=INK, width=1.6, dash="dot"))
    fig.update_layout(title="Componentes del índice por semana",
                      yaxis_title="0 a 100", height=h,
                      margin=dict(t=44, r=20, b=76, l=54))
    fig.update_yaxes(range=[0, 105], dtick=25)
    return fig
