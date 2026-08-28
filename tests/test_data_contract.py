"""
El fichero de eventos como sistema de registro.

Aquí el objeto del test es el dato, no el código. Dos cosas:

* **Contrato de entrada.** Lo que `SCHEMA.md` promete: ocho campos, orden
  temporal, enums cerrados. Si un fichero nuevo lo rompe, esto lo dice antes de
  que el error salga como un número raro en un gráfico.
* **Afirmaciones publicadas.** Cada cifra que el dashboard o las notas ponen en
  pantalla se recalcula aquí por un camino distinto. Una afirmación sin test es
  una afirmación que caduca en la siguiente recalibración.
"""

from __future__ import annotations

import json

import pytest

from balance.events import BLOCK, CATEGORIES, SENSITIVE, load
from conftest import DATA

CAMPOS = {"id", "event_type", "timestamp_millis", "package_name",
          "url_domain", "category", "block_type", "is_keyguard_locked"}
TIPOS = {"SCREEN_ON", "SCREEN_OFF", "USER_PRESENT", "APP_FOREGROUND",
         "URL_VISIT", "BLOCK"}
FICHEROS = ["events_user_a.json", "events_user_b.json"]


@pytest.fixture(scope="module", params=FICHEROS)
def crudo(request):
    return json.loads((DATA / request.param).read_text())


# ---------------------------------------------------------------------------
# Contrato de entrada
# ---------------------------------------------------------------------------

def test_todos_los_eventos_tienen_los_ocho_campos(crudo):
    for e in crudo:
        assert set(e) == CAMPOS


def test_los_tipos_de_evento_son_los_del_schema(crudo):
    assert {e["event_type"] for e in crudo} <= TIPOS


def test_las_categorias_son_las_del_enum(crudo):
    vistas = {e["category"] for e in crudo if e["category"]}
    assert vistas <= set(CATEGORIES)


def test_los_ids_son_monotonos_y_el_tiempo_va_en_orden(crudo):
    ids = [e["id"] for e in crudo]
    ts = [e["timestamp_millis"] for e in crudo]
    assert ids == sorted(ids)
    assert ts == sorted(ts)


def test_los_campos_aplican_a_su_tipo_de_evento(crudo):
    for e in crudo:
        t = e["event_type"]
        if t == "APP_FOREGROUND":
            assert e["package_name"] and e["category"]
            assert e["url_domain"] is None
        elif t == "URL_VISIT":
            assert e["url_domain"] and e["category"]
            assert e["package_name"] is None
        elif t == BLOCK:
            assert e["block_type"] in {"APP", "URL", "NUDITY"}
            assert e["package_name"] or e["url_domain"]
        elif t == "USER_PRESENT":
            assert e["is_keyguard_locked"] is False
        elif t == "SCREEN_OFF":
            assert e["is_keyguard_locked"] is None


def test_los_dominios_no_traen_ruta_ni_query(crudo):
    """SCHEMA.md promete sólo dominio. Si llegara una ruta, sería un dato
    personal que no debería estar ahí."""
    for e in crudo:
        d = e["url_domain"]
        if d:
            assert "/" not in d and "?" not in d and " " not in d


# ---------------------------------------------------------------------------
# Afirmaciones publicadas
# ---------------------------------------------------------------------------

def test_el_solapamiento_de_pantalla_existe_y_en_la_cantidad_declarada():
    """«77 SCREEN_ON en A y 411 en B con la pantalla ya encendida».

    Se cuenta con el mismo modelo de profundidad que usa `events.py`. Un modelo
    booleano (encendida/apagada, sin anidamiento) da 74 y 345: colapsa los
    solapes de profundidad 3, y ésas fueron las cifras que se publicaron por
    error antes de que este test existiera.
    """
    esperado = {"events_user_a.json": 77, "events_user_b.json": 411}
    for fichero, n in esperado.items():
        eventos = json.loads((DATA / fichero).read_text())
        depth = solapes = 0
        for e in eventos:
            if e["event_type"] == "SCREEN_ON":
                if depth > 0:
                    solapes += 1
                depth += 1
            elif e["event_type"] == "SCREEN_OFF":
                depth = max(0, depth - 1)
        assert solapes == n, f"{fichero}: {solapes} solapes, se declaran {n}"


def test_el_emparejamiento_elegido_cambia_el_resultado_en_ambos_sentidos():
    """Justifica el contador de profundidad con números, no con intuición.

    LIFO cuenta dos veces el solape y FIFO pierde el tramo sobrante. La unión
    queda en medio y, a diferencia de las otras dos, no depende de qué apagado
    se empareje con qué encendido.
    """
    tl = load(DATA / "events_user_a.json", "A")
    union_h = sum(i.seconds for i in tl.intervals) / 3600

    fifo_s, abierto = 0.0, None
    lifo_s, pila = 0.0, []
    for e in tl.events:
        t, ts_ = e["event_type"], e["timestamp_millis"]
        if t == "SCREEN_ON":
            if abierto is None:
                abierto = ts_
            pila.append(ts_)
        elif t == "SCREEN_OFF":
            if abierto is not None:
                fifo_s += (ts_ - abierto) / 1000
                abierto = None
            if pila:
                lifo_s += (ts_ - pila.pop()) / 1000

    assert round(union_h, 1) == 61.1
    assert round(fifo_s / 3600, 1) == 56.7, "FIFO se queda corto"
    assert round(lifo_s / 3600, 1) == 64.9, "LIFO se pasa"
    assert fifo_s / 3600 < union_h < lifo_s / 3600


def test_a_no_enciende_la_pantalla_de_madrugada(df_a):
    """La afirmación más repetida del dashboard."""
    assert df_a["night_min"].sum() == 0
    assert df_a["night_pickups"].sum() == 0


def test_a_no_registra_contenido_sensible(df_a):
    assert df_a["blocks_sensitive"].sum() == 0


def test_el_volumen_de_b_apenas_cambia_y_la_noche_se_multiplica(df_b):
    """«+8 % de pantalla, ×13 de madrugada entre la semana 1 y la 4»."""
    s1 = df_b[df_b.week == 1]["screen_min"].mean()
    s4 = df_b[df_b.week == 4]["screen_min"].mean()
    n1 = df_b[df_b.week == 1]["night_min"].mean()
    n4 = df_b[df_b.week == 4]["night_min"].mean()

    assert 1.05 < s4 / s1 < 1.12, "el volumen sube poco"
    assert n4 / n1 > 10, "la franja nocturna se multiplica por más de diez"


def test_la_ventana_de_sueno_de_b_se_encoge_unos_95_minutos(df_b):
    def w(col, k):
        return df_b[df_b.week == k][col].median()
    v1 = (24 + w("first_pickup_h", 1)) - w("night_end_h", 1)
    v4 = (24 + w("first_pickup_h", 4)) - w("night_end_h", 4)
    assert -140 < (v4 - v1) * 60 < -50


def test_los_bloqueos_de_a_caen_a_lo_largo_del_mes(df_a):
    """«de 19 en la semana 1 a 3 en la semana 4»."""
    assert df_a[df_a.week == 1]["blocks"].sum() == 19
    assert df_a[df_a.week == 4]["blocks"].sum() == 3


def test_los_intentos_sensibles_de_b_son_un_pico_no_una_tendencia(df_b):
    """«145 de 203 (71 %) en las semanas 2 y 3, y 30 en la 4»."""
    por_semana = df_b.groupby("week")["blocks_sensitive"].sum()
    total = por_semana.sum()
    assert total == 203
    assert por_semana.loc[[2, 3]].sum() == 145
    assert por_semana.loc[4] == 30


def test_la_persistencia_de_los_intentos_sensibles_es_baja(tl_b):
    """«ráfagas de 1,2 intentos de media, máximo 3» agrupando a 10 minutos."""
    sens = sorted((b for b in tl_b.blocks if b.category in SENSITIVE),
                  key=lambda b: b.ts_ms)
    rafagas, actual = [], [sens[0]]
    for b in sens[1:]:
        if b.ts_ms - actual[-1].ts_ms <= 10 * 60_000:
            actual.append(b)
        else:
            rafagas.append(actual)
            actual = [b]
    rafagas.append(actual)
    tam = [len(r) for r in rafagas]

    assert max(tam) == 3
    assert 1.1 <= sum(tam) / len(tam) <= 1.3


def test_la_cuota_de_distraccion_es_parecida_en_los_dos(df_a, df_b):
    """El contraintuitivo: el problema de B no es el reparto por categorías."""
    a = df_a["distract_share"].mean()
    b = df_b["distract_share"].mean()
    assert abs(a - b) < 0.05


def test_los_totales_de_bloqueos_cuadran(df_a, df_b):
    """Invariante: la suma por tipo es el total, sin solapes ni huecos."""
    for df in (df_a, df_b):
        por_tipo = df["blocks_app"] + df["blocks_url"] + df["blocks_nudity"]
        assert (por_tipo == df["blocks"]).all()


def test_la_cobertura_de_atribucion_es_la_declarada(tl_a, tl_b, df_a, df_b):
    """«86 % en A y 67 % en B»."""
    for tl, df, esperado in ((tl_a, df_a, 86), (tl_b, df_b, 67)):
        dias = set(df["day"])
        pantalla = sum(i.seconds for i in tl.intervals if i.day in dias)
        atribuido = sum(u.seconds for u in tl.usages if u.day in dias)
        assert round(atribuido / pantalla * 100) == esperado
