"""
El CLI como comprobación de que el motor existe fuera de la interfaz.

Si la única forma de ver los resultados fuese el dashboard, no habría manera de
distinguir un motor que calcula de una pantalla con números escritos a mano.
Estos tests ejercitan el mismo camino que un `cron` nocturno.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from balance.run import PROFILES, analyse, render_json, render_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module", params=list(PROFILES))
def resultado(request):
    return analyse(request.param, ROOT)


def test_el_analisis_es_una_funcion_pura_del_log():
    """Mismo fichero, mismo resultado: sin estado externo ni reloj."""
    a = render_json(analyse("B", ROOT))
    b = render_json(analyse("B", ROOT))
    assert a == b


def test_la_salida_de_texto_menciona_las_secciones(resultado):
    texto = render_text(resultado)
    for seccion in ("MEDIAS DEL PERIODO", "POR SEMANA", "AVISOS AL TUTOR",
                    "REFUERZOS", "NUDGE NOCTURNO", "EMISIONES DEL PERIODO"):
        assert seccion in texto


def test_el_json_es_serializable_y_no_lleva_tipos_de_numpy(resultado):
    """`json.dumps` sin `default=` sólo pasa si todo es tipo nativo."""
    crudo = json.dumps(render_json(resultado), ensure_ascii=False)
    vuelto = json.loads(crudo)
    assert vuelto["user"] == resultado["user"]
    assert isinstance(vuelto["averages"]["screen_min"], float)


def test_el_perfil_sin_tutor_no_emite_resumen(resultado):
    j = render_json(resultado)
    if not j["has_guardian"]:
        assert j["guardian_digest"] is None
        assert all(p["audience"] == "usuario" for p in j["positives"])


def test_el_cli_arranca_de_verdad():
    """Se ejecuta como subproceso: cubre el `argparse` y el `__main__`."""
    r = subprocess.run(
        [sys.executable, "-m", "balance.run", "--user", "A", "--format", "json"],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    datos = json.loads(r.stdout)
    assert datos[0]["user"] == "A"
    assert datos[0]["days"] == 30


def test_el_volcado_a_csv_escribe_los_dos_frames(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "balance.run", "--user", "B",
         "--format", "json", "--csv", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "daily_B.csv").exists()
    assert (tmp_path / "weekly_B.csv").exists()


def test_el_cli_y_el_dashboard_calculan_lo_mismo():
    """Las dos interfaces son adaptadores sobre el mismo núcleo, no dos
    implementaciones que se puedan desincronizar."""
    from balance.events import load
    from balance.intelligence import evaluate_alerts
    from balance.metrics import daily_frame
    from balance.score import add_score

    directo = add_score(daily_frame(load(ROOT / "data/events_user_b.json", "B")))
    via_cli = analyse("B", ROOT)["daily"]
    assert directo["score"].tolist() == via_cli["score"].tolist()
    assert ([s.key for s in evaluate_alerts(directo)]
            == [s.key for s in analyse("B", ROOT)["alerts"]])
