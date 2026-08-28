"""
Capa 1: definiciones de las métricas diarias.

Cada test fija una decisión que se toma en `metrics.py` y que no es obvia
leyendo el schema: dónde corta la noche, dónde empieza el día, qué se hace con
un día truncado.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from balance.metrics import WAKE_END, WAKE_START, daily_frame, weekly_frame
from conftest import DAY0, build, ev


def _frame(events, tmp_path):
    return daily_frame(build(events, tmp_path=tmp_path))


def _dia_completo(day_offset: int) -> list[dict]:
    """Actividad de relleno que hace que un día supere el umbral de cobertura.

    `daily_frame` descarta los días que el fichero sólo cubre en parte; sin este
    relleno, cualquier stream sintético corto se caería entero del frame.
    """
    return [
        ev("SCREEN_ON", day_offset, "07:00", is_keyguard_locked=True),
        ev("USER_PRESENT", day_offset, "07:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", day_offset, "07:05"),
        ev("SCREEN_ON", day_offset, "21:00", is_keyguard_locked=True),
        ev("USER_PRESENT", day_offset, "21:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", day_offset, "21:05"),
    ]


def test_la_noche_va_de_las_23_a_las_6_del_dia_siguiente(tmp_path):
    """El día natural corta a medianoche, la noche no: si no, una misma noche
    aparece partida en dos filas y la señal se diluye."""
    df = _frame(
        _dia_completo(0) + [
            ev("SCREEN_ON", 0, "23:30", is_keyguard_locked=True),
            ev("USER_PRESENT", 0, "23:30:02", is_keyguard_locked=False),
            ev("SCREEN_OFF", 1, "00:30"),
        ] + _dia_completo(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_min"] == 60, "los 60 minutos son de la noche del día 0"
    assert df.loc[DAY0 + dt.timedelta(days=1), "night_min"] == 0
    # y el screen time diario sigue partido a medianoche
    assert round(df.loc[DAY0, "screen_min"]) == 10 + 30
    assert round(df.loc[DAY0 + dt.timedelta(days=1), "screen_min"]) == 30 + 10


def test_el_primer_desbloqueo_tiene_suelo_a_las_6(tmp_path):
    """Un día que arranca a las 00:20 no ha empezado: no ha terminado el
    anterior. Ese fenómeno se mide en `night_*`, no en `first_pickup_h`."""
    df = _frame([
        ev("SCREEN_ON", 0, "00:20", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "00:20:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "00:50"),
    ] + _dia_completo(0), tmp_path=tmp_path)

    assert df.loc[DAY0, "first_pickup_h"] == 7.0, \
        "el desbloqueo de las 00:20 no cuenta como inicio del día"


def test_la_madrugada_pertenece_a_la_noche_del_dia_anterior(tmp_path):
    """Consecuencia de definir la noche como 23:00 → 06:00 del día siguiente.

    Media hora de pantalla a las 00:20 del día 1 se contabiliza en la noche del
    día 0, no en la del 1. Es la convención correcta (es la misma noche), pero
    tiene un borde: la madrugada del **primer** día del periodo pertenece a una
    noche anterior al dato y por tanto no se contabiliza en ninguna fila.
    """
    df = _frame(_dia_completo(0) + [
        ev("SCREEN_ON", 1, "00:20", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "00:20:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:50"),
    ] + _dia_completo(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_min"] == 30, "se imputa a la noche del día 0"
    assert df.loc[DAY0 + dt.timedelta(days=1), "night_min"] == 0


def test_la_hora_de_ultimo_uso_no_baja_al_acostarse_mas_tarde(tmp_path):
    """El eje se desplaza a las 04:00: la madrugada sale como 24–28.

    Sin esto, acostarse a la 01:00 se registra como `1.0` y la media de "hora de
    última pantalla" *baja* cuando el usuario se acuesta más tarde, que es lo
    contrario de lo que ocurre.
    """
    df = _frame(_dia_completo(0) + [
        ev("SCREEN_ON", 0, "23:50", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "23:50:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "01:00"),
    ] + _dia_completo(1), tmp_path=tmp_path)

    assert df.loc[DAY0, "night_end_h"] == 25.0, "01:00 se expresa como 25:00"


def test_los_dias_truncados_por_el_borde_del_fichero_se_excluyen(tmp_path):
    """El fichero de user_b acaba a las 00:46 del 31. Ese día tiene 0,8 h de
    cobertura y promediarlo hunde las medias del mes."""
    df = _frame(_dia_completo(0) + [
        ev("SCREEN_ON", 1, "00:10", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "00:10:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:40"),
    ], tmp_path=tmp_path)

    assert list(df["day"]) == [DAY0], "el día 1 sólo tiene 40 min de cobertura"
    # pero sus eventos sí cuentan para la noche del día 0
    assert df.loc[DAY0, "night_min"] == 30


def test_los_cambios_de_app_se_reinician_cada_dia(tmp_path):
    """Sin reinicio, la primera app de la mañana cuenta como cambio respecto a
    la última de la noche anterior: un cambio falso por día."""
    events = []
    for d in (0, 1):
        events += [
            ev("SCREEN_ON", d, "09:00", is_keyguard_locked=True),
            ev("USER_PRESENT", d, "09:00:02", is_keyguard_locked=False),
            ev("APP_FOREGROUND", d, "09:01", package_name="com.whatsapp",
               category="MESSAGING"),
            ev("APP_FOREGROUND", d, "09:03", package_name="com.spotify.music",
               category="ENTERTAINMENT"),
            ev("SCREEN_OFF", d, "09:05"),
        ] + _dia_completo(d)
    df = _frame(events, tmp_path=tmp_path)

    assert list(df["app_switches"]) == [1, 1], \
        "un cambio por día, no dos en el segundo"


def test_desconexion_mas_larga_dentro_de_la_vigilia(tmp_path):
    """Se mide sólo entre las 07:00 y las 23:00: dormir no es mérito."""
    df = _frame([
        ev("SCREEN_ON", 0, "07:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "07:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "08:00"),
        ev("SCREEN_ON", 0, "14:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "14:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "14:10"),
        ev("SCREEN_ON", 0, "22:55", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "22:55:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "22:59"),
    ], tmp_path=tmp_path)

    # huecos dentro de la vigilia: 08:00→14:00 (6 h) y 14:10→22:55 (8 h 45).
    assert df.loc[DAY0, "longest_offline_s"] == 8 * 3600 + 45 * 60


def test_offline_en_vigilia_complementa_a_la_pantalla(tmp_path):
    """Pantalla + offline tienen que sumar la ventana de vigilia entera."""
    df = _frame(_dia_completo(0), tmp_path=tmp_path)
    ventana_s = (WAKE_END - WAKE_START) * 3600
    fila = df.loc[DAY0]
    assert abs(fila["screen_wake_s"] + fila["offline_wake_s"] - ventana_s) < 1


def test_el_screen_time_diario_suma_exactamente_sus_tramos(tl_a, df_a):
    """Invariante sobre el dato real: la fila del día es la suma de sus tramos."""
    por_dia = {}
    for iv in tl_a.intervals:
        por_dia[iv.day] = por_dia.get(iv.day, 0) + iv.seconds
    for day, screen_s in zip(df_a["day"], df_a["screen_s"]):
        assert abs(por_dia[day] - screen_s) < 1e-6


def test_pickups_mas_vistazos_igualan_los_screen_on(tl_a):
    """Todo SCREEN_ON acaba clasificado, sin perder ni duplicar ninguno."""
    n_on = sum(1 for e in tl_a.events if e["event_type"] == "SCREEN_ON")
    clasificados = sum(i.pickups + i.glances for i in tl_a.intervals)
    huerfanos = tl_a.anomalies.get("USER_PRESENT sin SCREEN_ON", 0)
    assert clasificados - huerfanos == n_on


def test_las_semanas_incompletas_se_marcan(df_b):
    w = weekly_frame(df_b)
    assert w.loc[w["days"] == 7, "is_partial"].eq(False).all()
    assert w.loc[w["days"] < 7, "is_partial"].all()


def test_la_carga_es_determinista(tmp_path):
    """Mismo fichero, mismo resultado: la derivación es una función pura del
    log de eventos, no depende de estado externo ni de la hora de ejecución."""
    from balance.events import load
    from conftest import DATA
    a = daily_frame(load(DATA / "events_user_a.json", "A"))
    b = daily_frame(load(DATA / "events_user_a.json", "A"))
    pd.testing.assert_frame_equal(
        a.drop(columns=["_cat_s", "_app_s", "_site_s"]),
        b.drop(columns=["_cat_s", "_app_s", "_site_s"]))


def test_la_racha_mas_larga_guarda_cuando_empieza(tmp_path):
    """El enunciado pide contexto, no sólo duración: «your longest break was
    Saturday afternoon». Sin el cuándo, una racha es sólo un número."""
    # 1 de mayo de 2026 es viernes; el 2 es sábado.
    df = _frame(_dia_completo(1) + [
        ev("SCREEN_ON", 1, "10:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "10:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "10:05"),
        ev("SCREEN_ON", 1, "17:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 1, "17:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "17:05"),
    ], tmp_path=tmp_path)

    fila = df.iloc[0]
    assert fila["longest_offline_when"] == "el sábado al mediodía"
    assert fila["longest_offline_h"] == pytest.approx(6.92, abs=0.02)


def test_el_cuando_de_la_racha_nunca_falta_en_el_dato_real(df_a, df_b):
    for df in (df_a, df_b):
        assert df["longest_offline_when"].notna().all()
        assert df["longest_offline_h"].gt(0).all()
