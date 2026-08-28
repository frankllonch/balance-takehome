"""
Capa 4: qué se avisa, a quién, y qué se calla.

Tres grupos de test:

* **Comportamiento sobre el dato real.** Las afirmaciones que el dashboard hace
  en pantalla ("night_drift salta el 19 de mayo", "screen_jump no dispara en
  ninguno") se convierten aquí en aserciones. Si una recalibración las rompe,
  el test lo dice antes que el lector.
* **Propiedades del reparto.** Cupos, separación mínima, cadencia.
* **El contrato de privacidad.** Lo que sale hacia el tutor no puede contener
  nombres de app, dominios ni categorías.
"""

from __future__ import annotations

import datetime as dt
import json

from balance.events import CATEGORIES
from balance.intelligence import (
    ALERT_BUDGET, ALERT_MIN_GAP_DAYS, POS_BUDGET_DAYS, emissions,
    evaluate_alerts, evaluate_positives, guardian_digest, month_replay,
    nudge_summary, replay_nudge,
)


# ---------------------------------------------------------------------------
# Avisos al tutor
# ---------------------------------------------------------------------------

def test_night_drift_salta_el_19_de_mayo_solo_en_b(df_a, df_b):
    a = [s for s in evaluate_alerts(df_a) if s.key == "night_drift"]
    b = [s for s in evaluate_alerts(df_b) if s.key == "night_drift"]
    assert a == [], "el usuario A no tiene deriva nocturna que detectar"
    assert len(b) == 1
    assert b[0].day == dt.date(2026, 5, 19)
    assert b[0].decision == "enviada"


def test_screen_jump_no_dispara_en_ninguno(df_a, df_b):
    """Control negativo: la regla de volumen convencional.

    Es la que casi cualquier implementación pondría primero, y con estos datos
    no detecta nada: el uso diario de B sube un 8 % mientras su franja nocturna
    se multiplica por 13.
    """
    for df in (df_a, df_b):
        assert [s for s in evaluate_alerts(df) if s.key == "screen_jump"] == []


def test_el_pico_de_contenido_sensible_no_se_notifica(df_b):
    """Se detecta y baja a resumen semanal: el filtro ya lo paró, y la
    conversación que queda no gana nada por llegar hoy."""
    spike = [s for s in evaluate_alerts(df_b) if s.key == "sensitive_spike"]
    assert len(spike) == 1
    assert spike[0].decision == "resumen"
    assert spike[0].actionability < 0.5


def test_el_cupo_de_avisos_se_respeta(df_a, df_b):
    for df in (df_a, df_b):
        enviadas = [s for s in evaluate_alerts(df) if s.decision == "enviada"]
        assert len(enviadas) <= ALERT_BUDGET
        fechas = sorted(s.day for s in enviadas)
        for x, y in zip(fechas, fechas[1:]):
            assert (y - x).days >= ALERT_MIN_GAP_DAYS


def test_cada_señal_descartada_lleva_motivo(df_b):
    for s in evaluate_alerts(df_b):
        if s.decision != "enviada":
            assert s.reason, f"{s.key} se descarta sin explicar por qué"


def test_una_racha_de_dias_es_un_episodio_no_uno_por_dia(df_b):
    """La regla se cumple del 19 al 23 de mayo. Eso es un hecho, no cinco."""
    drift = [s for s in evaluate_alerts(df_b) if s.key == "night_drift"][0]
    assert drift.days_true == 5
    assert drift.until == dt.date(2026, 5, 23)


# ---------------------------------------------------------------------------
# Refuerzos
# ---------------------------------------------------------------------------

def test_el_perfil_sano_recibe_refuerzos(df_a):
    """Un sistema que sólo habla cuando algo empeora se lee como una amenaza."""
    pos = [s for s in evaluate_positives(df_a, has_guardian=False)
           if s.decision == "enviada"]
    assert len(pos) >= 2
    assert all(s.audience == "usuario" for s in pos)


def test_sin_tutor_no_se_generan_refuerzos_para_tutor(df_a):
    pos = evaluate_positives(df_a, has_guardian=False)
    assert all(s.audience != "tutor" for s in pos)


def test_el_tutor_de_b_recibe_aviso_y_refuerzo(df_b):
    """El canal al tutor no puede ser sólo malas noticias."""
    avisos = [s for s in evaluate_alerts(df_b) if s.decision == "enviada"]
    refuerzos = [s for s in evaluate_positives(df_b, True)
                 if s.decision == "enviada" and s.audience == "tutor"]
    assert len(avisos) == 1 and len(refuerzos) == 1


def test_el_cupo_de_refuerzos_separa_al_menos_una_semana(df_a, df_b):
    for df, hg in ((df_a, False), (df_b, True)):
        enviados = [s for s in evaluate_positives(df, hg)
                    if s.decision == "enviada"]
        por_audiencia = {}
        for s in sorted(enviados, key=lambda x: x.day):
            prev = por_audiencia.get(s.audience)
            if prev:
                assert (s.day - prev).days >= POS_BUDGET_DAYS
            por_audiencia[s.audience] = s.day


def test_los_refuerzos_no_dan_instrucciones(df_a, df_b):
    """El tono es descriptivo. Si aparece una recomendación, el test la caza."""
    prohibidas = ("deberías", "deberia", "intenta", "prueba a", "te recomend",
                  "buen momento para", "podrías", "recuerda que deb")
    for df, hg in ((df_a, False), (df_b, True)):
        for s in evaluate_positives(df, hg) + evaluate_alerts(df):
            texto = s.guardian_text.lower()
            for frase in prohibidas:
                assert frase not in texto, f"{s.key}: «{s.guardian_text}»"


# ---------------------------------------------------------------------------
# Nudge en dispositivo
# ---------------------------------------------------------------------------

def test_el_nudge_no_dispara_en_el_perfil_sano(tl_a, df_a):
    ns = nudge_summary(replay_nudge(tl_a, df_a))
    assert ns["noches con aviso"] == 0, "cero falsos positivos sin configurar nada"


def test_el_nudge_dispara_en_b_y_deja_margen_medible(tl_b, df_b):
    ns = nudge_summary(replay_nudge(tl_b, df_b))
    assert ns["noches con aviso"] == 14
    assert 0.30 < ns["cuota del total nocturno"] < 0.45


def test_toda_noche_sin_nudge_tiene_motivo(tl_b, df_b):
    for n in replay_nudge(tl_b, df_b):
        assert n.fired or n.quiet_reason, f"{n.day}: ni dispara ni explica"


# ---------------------------------------------------------------------------
# Contrato de privacidad
# ---------------------------------------------------------------------------

def _texto_hacia_el_tutor(tl, df, has_guardian: bool) -> str:
    """Todo lo que saldría del dispositivo hacia un tutor, concatenado."""
    sigs = evaluate_alerts(df) + evaluate_positives(df, has_guardian)
    piezas = [s.guardian_text for s in sigs
              if s.audience == "tutor" and s.decision == "enviada"]
    piezas += [s.headline for s in sigs
               if s.audience == "tutor" and s.decision == "enviada"]
    piezas.append(json.dumps(guardian_digest(df, sigs), ensure_ascii=False))
    return " ".join(piezas).lower()


def test_el_payload_del_tutor_no_contiene_apps_ni_dominios(tl_b, df_b):
    """El contrato de privacidad, como aserción y no como promesa del README."""
    fuera = _texto_hacia_el_tutor(tl_b, df_b, True)

    paquetes = {e["package_name"] for e in tl_b.events if e["package_name"]}
    dominios = {e["url_domain"] for e in tl_b.events if e["url_domain"]}

    # Se comprueba el identificador completo y también su raíz ("pornhub" de
    # pornhub.com, "whatsapp" de com.whatsapp), que es como se filtraría de
    # verdad un dato. Raíces de menos de cuatro letras se saltan: la "x" de
    # x.com aparece en cualquier texto en castellano y daría falso positivo.
    def raices(ident: str) -> list[str]:
        partes = [ident] + ident.replace("/", ".").split(".")
        return [p.lower() for p in partes if len(p) >= 4]

    for ident in paquetes | dominios:
        for raiz in raices(ident):
            assert raiz not in fuera, f"«{raiz}» se ha filtrado al tutor"


def test_el_payload_del_tutor_no_nombra_categorias(tl_b, df_b):
    fuera = _texto_hacia_el_tutor(tl_b, df_b, True)
    for cat in CATEGORIES:
        assert cat.lower() not in fuera


def test_el_resumen_al_tutor_va_redondeado(df_b):
    """Un valor fino («247 minutos, índice 41,3») identifica a una persona."""
    d = guardian_digest(df_b, evaluate_alerts(df_b))
    assert d["pantalla al día"].endswith("h aprox.")
    indice = int(d["índice de bienestar"].split()[0])
    assert indice % 5 == 0, "el índice sale en múltiplos de 5"
    assert d["contenido sensible abierto"] == "ninguno"


def test_ningun_contenido_sensible_llego_a_abrirse(tl_a, tl_b):
    """La afirmación que el resumen del tutor transmite, verificada en el
    stream: no hay ni un URL_VISIT ni un APP_FOREGROUND con esas categorías."""
    from balance.events import SENSITIVE
    for tl in (tl_a, tl_b):
        abiertos = [e for e in tl.events
                    if e["event_type"] in ("URL_VISIT", "APP_FOREGROUND")
                    and e["category"] in SENSITIVE]
        assert abiertos == []


# ---------------------------------------------------------------------------
# Recorrido del mes
# ---------------------------------------------------------------------------

def test_el_recorrido_no_reinicia_el_cupo_de_refuerzos(tl_b, df_b):
    """Bug real: recalcular los refuerzos por prefijo reiniciaba el cupo cada
    día y multiplicaba los envíos. Deben coincidir con el cálculo único."""
    pos = evaluate_positives(df_b, True)
    replay = month_replay(df_b, replay_nudge(tl_b, df_b), pos)
    en_recorrido = sum(len(r["positives"]) for r in replay)
    esperados = sum(1 for s in pos if s.decision == "enviada")
    assert en_recorrido == esperados


def test_el_recorrido_solo_usa_informacion_pasada(tl_b, df_b):
    """El teléfono del día 12 no sabía lo que iba a pasar el 19."""
    replay = month_replay(df_b, replay_nudge(tl_b, df_b),
                          evaluate_positives(df_b, True))
    for r in replay:
        if r["alert"]:
            assert r["alert"].day == r["day"]
        assert r["alerts_so_far"] <= ALERT_BUDGET


def test_las_emisiones_cubren_los_tres_destinos(tl_b, df_b):
    replay = month_replay(df_b, replay_nudge(tl_b, df_b),
                          evaluate_positives(df_b, True))
    destinos = {e["destino"] for e in emissions(replay)}
    assert "Usuario · pantalla" in destinos
    assert "Tutor · notificación" in destinos
    assert "Tutor · refuerzo" in destinos
