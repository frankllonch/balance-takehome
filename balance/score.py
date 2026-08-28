"""
Capa 2 · un único número de 0 a 100 por día.

Cinco componentes, cada uno 0–100, ponderados. El diseño y sus grietas están
explicados en el README; el resumen es:

* **Anclaje absoluto, narrativa personal.** El score se mide contra bandas
  fijas, no contra el pasado del usuario. Si fuera relativo, alguien que lleva
  6 h/día constantes sacaría 100 por ser constante, y el número dejaría de
  significar nada. La comparación con uno mismo va *al lado* del número
  (`*_delta` en `metrics.py`), no dentro de él.

* **Los bloqueos no puntúan.** Un BLOCK significa que el teléfono hizo su
  trabajo: el contenido no llegó a abrirse. Penalizar el intento sería
  castigar al usuario por un impulso que el producto ya ha resuelto, y crearía
  el incentivo equivocado (desactivar la protección para "subir nota"). Los
  bloqueos alimentan el aviso al tutor y el nudge, no el score.

* **La noche pesa mucho para lo poco que ocupa.** 60 min de pantalla a las
  01:00 hacen más daño que 60 min a las 17:00, y son mucho más fáciles de
  corregir. Es la palanca con mejor relación esfuerzo/beneficio.
"""

from __future__ import annotations

import pandas as pd

#: (columna, etiqueta, valor_para_100, valor_para_0, peso)
COMPONENTS = [
    ("screen_min",        "Tiempo de pantalla",  90,    360,  0.25),
    ("pickups",           "Fragmentación",       15,     60,  0.20),
    ("night_min",         "Noche protegida",      0,     60,  0.20),
    ("longest_offline_h", "Desconexión larga",    4,      1,  0.15),
    ("distract_share",    "Intención",         0.10,   0.50,  0.20),
]

WEIGHTS = {c[0]: c[4] for c in COMPONENTS}
LABELS = {c[0]: c[1] for c in COMPONENTS}


def _band(x: float, good: float, bad: float) -> float:
    """Interpolación lineal entre `good`→100 y `bad`→0, recortada a [0,100].
    Funciona en los dos sentidos (good < bad y good > bad)."""
    if pd.isna(x):
        return 50.0
    if good < bad:                       # menos es mejor
        return float(max(0.0, min(100.0, 100 * (bad - x) / (bad - good))))
    return float(max(0.0, min(100.0, 100 * (x - bad) / (good - bad))))


def add_score(df: pd.DataFrame) -> pd.DataFrame:
    """Añade `score` y `score_<componente>` al frame diario."""
    df = df.copy()
    total = pd.Series(0.0, index=df.index)
    for col, _label, good, bad, weight in COMPONENTS:
        s = df[col].map(lambda v: _band(v, good, bad))
        df[f"score_{col}"] = s
        total += s * weight
    df["score"] = total.round(1)

    # media móvil de 7 días: el score diario es ruidoso, la tendencia no.
    df["score_7d"] = df["score"].rolling(7, min_periods=3).mean()
    return df


def contributions(row: pd.Series) -> pd.DataFrame:
    """Descomposición de un día: cuántos puntos aporta y cuántos pierde cada
    componente. Es lo que hace el score explicable en vez de mágico."""
    return pd.DataFrame([{
        "component": label,
        "raw": row[col],
        "score": row[f"score_{col}"],
        "weight": weight,
        "points": row[f"score_{col}"] * weight,
        "lost": (100 - row[f"score_{col}"]) * weight,
    } for col, label, _g, _b, weight in COMPONENTS])
