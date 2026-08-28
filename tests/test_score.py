"""
Capa 2: el índice de bienestar.

Lo que se prueba aquí no es "el número sale 83", que cambiaría con cualquier
recalibración, sino las propiedades que el índice debe cumplir sea cual sea la
calibración: rango acotado, monotonía en el sentido correcto, pesos que suman
uno, y la decisión de producto de que los bloqueos no puntúen.
"""

from __future__ import annotations

import pandas as pd
import pytest

from balance.score import COMPONENTS, _band, add_score, contributions


def test_los_pesos_suman_uno():
    assert abs(sum(w for *_r, w in COMPONENTS) - 1.0) < 1e-9


def test_la_banda_interpola_y_recorta():
    # menos es mejor
    assert _band(90, 90, 360) == 100
    assert _band(360, 90, 360) == 0
    assert _band(10, 90, 360) == 100, "por debajo del ideal no se pasa de 100"
    assert _band(9999, 90, 360) == 0, "por encima del peor no baja de 0"
    assert _band(225, 90, 360) == pytest.approx(50)
    # más es mejor
    assert _band(4, 4, 1) == 100
    assert _band(1, 4, 1) == 0
    assert _band(2.5, 4, 1) == pytest.approx(50)


def test_un_dato_ausente_no_rompe_el_indice():
    """Un NaN puntúa 50, no propaga NaN al total."""
    assert _band(float("nan"), 90, 360) == 50.0


def test_el_indice_esta_acotado(df_a, df_b):
    for df in (df_a, df_b):
        assert df["score"].between(0, 100).all()


@pytest.mark.parametrize("col,peor", [
    ("screen_min", 600), ("pickups", 200), ("night_min", 300),
])
def test_empeorar_una_metrica_baja_el_indice(df_a, col, peor):
    """Monotonía: si una entrada empeora, el índice no puede subir."""
    peor_df = add_score(df_a.assign(**{col: peor}))
    assert peor_df["score"].mean() < df_a["score"].mean()


def test_los_bloqueos_no_puntuan(df_b):
    """Decisión de producto, no detalle de implementación.

    Un BLOCK significa que el filtro actuó y el contenido no se abrió. Si
    descontase puntos, el usuario tendría el incentivo de desactivar la
    protección para subir nota.
    """
    sin_bloqueos = add_score(df_b.assign(blocks=0, blocks_sensitive=0,
                                         blocks_app=0, blocks_url=0,
                                         blocks_nudity=0))
    pd.testing.assert_series_equal(sin_bloqueos["score"], df_b["score"])


def test_la_descomposicion_suma_el_indice(df_b):
    """El índice tiene que ser explicable: la suma de aportaciones es el total."""
    fila = df_b.iloc[10]
    c = contributions(fila)
    assert c["points"].sum() == pytest.approx(fila["score"], abs=0.05)
    assert (c["points"] + c["lost"]).sum() == pytest.approx(100, abs=1e-6)


def test_los_componentes_estan_acotados(df_b):
    for col, *_ in COMPONENTS:
        assert df_b[f"score_{col}"].between(0, 100).all()
