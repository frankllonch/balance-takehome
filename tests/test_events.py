"""
Capa 0: reconstrucción de pantalla, sesiones y atribución de tiempo.

Es la capa donde se decide si todo lo demás es cierto, y la única que trata con
un stream que no viene limpio. Cada caso raro observado en los ficheros reales
tiene aquí su test sintético.
"""

from __future__ import annotations

import datetime as dt

from balance.events import MAX_FOREGROUND_S
from conftest import DAY0, build, ev, ts


def test_pickup_simple(tmp_path):
    """ON seguido de USER_PRESENT es un desbloqueo real, no un vistazo."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:05", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:10"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].pickups == 1
    assert tl.intervals[0].glances == 0
    assert tl.intervals[0].seconds == 600


def test_glance_sin_desbloqueo(tmp_path):
    """ON sin USER_PRESENT es un vistazo: la pantalla se encendió, el teléfono
    no se abrió."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:00:12"),
    ], tmp_path=tmp_path)

    assert tl.intervals[0].pickups == 0
    assert tl.intervals[0].glances == 1
    assert tl.intervals[0].is_pickup is False


def test_tramos_solapados_son_un_solo_intervalo(tmp_path):
    """El caso que rompe el emparejado ingenuo.

    ON(09:00) ON(09:04) OFF(09:06) OFF(09:11) aparece 74 veces en user_a y 345
    en user_b. Emparejando por pares saldrían 2+5=7 minutos; físicamente la
    pantalla estuvo encendida de 09:00 a 09:11, que son 11.
    """
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("SCREEN_ON", 0, "09:04", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:04:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:06"),
        ev("SCREEN_OFF", 0, "09:11"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1, "la unión es un solo tramo, no dos"
    assert tl.intervals[0].seconds == 11 * 60
    assert tl.intervals[0].pickups == 2, "los dos desbloqueos siguen contando"


def test_dos_on_seguidos_sin_desbloqueo_son_dos_vistazos(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_ON", 0, "09:01", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:02"),
        ev("SCREEN_OFF", 0, "09:03"),
    ], tmp_path=tmp_path)

    assert tl.intervals[0].glances == 2
    assert tl.intervals[0].pickups == 0


def test_user_present_sin_screen_on_abre_tramo(tmp_path):
    """Cuatro casos así en user_b. Se abre tramo y se registra la anomalía."""
    tl = build([
        ev("USER_PRESENT", 0, "09:00", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:05"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].seconds == 300
    assert tl.anomalies["USER_PRESENT sin SCREEN_ON"] == 1


def test_screen_off_con_pantalla_apagada_se_ignora(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("SCREEN_OFF", 0, "09:05"),
        ev("SCREEN_OFF", 0, "09:06"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.anomalies["SCREEN_OFF con pantalla apagada"] == 1


def test_tramo_que_cruza_medianoche_se_parte(tmp_path):
    """El screen time diario tiene que sumar exactamente el día."""
    tl = build([
        ev("SCREEN_ON", 0, "23:40", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "23:40:05", is_keyguard_locked=False),
        ev("SCREEN_OFF", 1, "00:20"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 2
    a, b = tl.intervals
    assert a.day == DAY0 and b.day == DAY0 + dt.timedelta(days=1)
    assert a.seconds == 20 * 60 and b.seconds == 20 * 60
    assert a.pickups == 1 and b.pickups == 0, \
        "el desbloqueo pertenece al día en que se produjo"


def test_fichero_que_acaba_con_la_pantalla_encendida(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.anomalies["tramo abierto al final del fichero"] == 1
    assert tl.intervals[0].end_ms == ts(0, "09:01")


# ---------------------------------------------------------------------------
# Atribución de tiempo
# ---------------------------------------------------------------------------

def test_tiempo_de_app_hasta_el_siguiente_foreground(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("APP_FOREGROUND", 0, "09:04", package_name="com.spotify.music",
           category="ENTERTAINMENT"),
        ev("SCREEN_OFF", 0, "09:10"),
    ], tmp_path=tmp_path)

    por_app = {u.key: u.seconds for u in tl.usages}
    assert por_app["com.whatsapp"] == 3 * 60
    assert por_app["com.spotify.music"] == 6 * 60


def test_el_dominio_le_quita_el_tiempo_al_navegador(tmp_path):
    """Chrome es un contenedor, no un destino: el tiempo va al dominio."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:00:10", package_name="com.android.chrome",
           category="OTHER"),
        ev("URL_VISIT", 0, "09:01", url_domain="bbc.com", category="NEWS"),
        ev("SCREEN_OFF", 0, "09:06"),
    ], tmp_path=tmp_path)

    por_clave = {u.key: u.seconds for u in tl.usages}
    assert por_clave["com.android.chrome"] == 50
    assert por_clave["bbc.com"] == 5 * 60


def test_eventos_con_pantalla_apagada_no_generan_tiempo(tmp_path):
    """Música de fondo y sincronizaciones. 17 casos en user_a, 344 en user_b."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("SCREEN_OFF", 0, "09:05"),
        ev("APP_FOREGROUND", 0, "09:30", package_name="com.spotify.music",
           category="ENTERTAINMENT"),
    ], tmp_path=tmp_path)

    assert tl.usages == []
    assert tl.anomalies["APP_FOREGROUND con pantalla apagada"] == 1


def test_un_bloque_cierra_el_foreground_pero_no_consume_tiempo(tmp_path):
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("BLOCK", 0, "09:03", package_name="com.instagram.android",
           category="SOCIAL_MEDIA", block_type="APP"),
        ev("SCREEN_OFF", 0, "09:05"),
    ], tmp_path=tmp_path)

    assert {u.key for u in tl.usages} == {"com.whatsapp"}
    assert tl.usages[0].seconds == 2 * 60
    assert len(tl.blocks) == 1
    assert tl.blocks[0].block_type == "APP"


def test_tope_de_primer_plano(tmp_path):
    """Si falta el SCREEN_OFF, una app no puede acumular horas."""
    tl = build([
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
        ev("APP_FOREGROUND", 0, "09:01", package_name="com.whatsapp",
           category="MESSAGING"),
        ev("SCREEN_OFF", 0, "23:00"),
    ], tmp_path=tmp_path)

    assert tl.usages[0].seconds == MAX_FOREGROUND_S


def test_los_eventos_se_ordenan_aunque_lleguen_desordenados(tmp_path):
    """El schema promete orden temporal, pero `load` no se fía."""
    tl = build([
        ev("SCREEN_OFF", 0, "09:10"),
        ev("SCREEN_ON", 0, "09:00", is_keyguard_locked=True),
        ev("USER_PRESENT", 0, "09:00:02", is_keyguard_locked=False),
    ], tmp_path=tmp_path)

    assert len(tl.intervals) == 1
    assert tl.intervals[0].seconds == 600
