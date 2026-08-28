"""
CLI: el mismo motor que el dashboard, sin dashboard.

    python -m balance.run                    # los dos perfiles, texto
    python -m balance.run --user B           # sólo B
    python -m balance.run --format json      # para encadenar con jq
    python -m balance.run --csv salida/      # frames diarios y semanales

Existe por dos razones. La primera es de comprobación: si el único sitio donde
se ven los resultados es una interfaz, no hay forma de distinguir un motor que
funciona de una pantalla con números escritos a mano. La segunda es operativa:
es el punto de entrada natural para un `cron` nocturno o para un proceso de
ingesta, sin arrastrar Streamlit como dependencia.

`balance/` no importa Streamlit ni Plotly en ninguna capa de cálculo, así que
este módulo corre con pandas y poco más.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path

from .events import load
from .intelligence import (
    emissions, evaluate_alerts, evaluate_positives, guardian_digest,
    month_replay, nudge_summary, replay_nudge,
)
from .metrics import blocks_frame, daily_frame, totals, weekly_frame
from .score import add_score

#: Ficheros de entrada y si el perfil tiene tutor asignado. En producción esto
#: vendría de la cuenta, no de una constante.
PROFILES = {
    "A": {"path": "data/events_user_a.json", "guardian": False},
    "B": {"path": "data/events_user_b.json", "guardian": True},
}


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------

def analyse(user: str, root: Path) -> dict:
    """Todo lo que el sistema deriva de un fichero de eventos.

    Es una función pura del log: mismo fichero, mismo resultado, sin estado
    externo ni dependencia de la hora de ejecución.
    """
    cfg = PROFILES[user]
    tl = load(root / cfg["path"], user)
    df = add_score(daily_frame(tl))
    days = set(df["day"])

    nudges = replay_nudge(tl, df)
    alerts = evaluate_alerts(df)
    positives = evaluate_positives(df, cfg["guardian"])
    replay = month_replay(df, nudges, positives)

    return {
        "user": user,
        "has_guardian": cfg["guardian"],
        "timeline": tl,
        "daily": df,
        "weekly": weekly_frame(df),
        "apps": totals(tl, df, "app"),
        "sites": totals(tl, df, "site"),
        "blocks": blocks_frame(tl, days),
        "alerts": alerts,
        "positives": positives,
        "nudges": nudges,
        "nudge_summary": nudge_summary(nudges),
        "digest": guardian_digest(df, alerts),
        "emissions": emissions(replay),
    }


# ---------------------------------------------------------------------------
# Salida en texto
# ---------------------------------------------------------------------------

def _rule(title: str = "", width: int = 76) -> str:
    if not title:
        return "─" * width
    return f"── {title} " + "─" * max(0, width - len(title) - 4)


def _hm(minutes: float) -> str:
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h{m:02d}" if h else f"{m}min"


def render_text(r: dict) -> str:
    df, w = r["daily"], r["weekly"]
    tl = r["timeline"]
    out: list[str] = []
    add = out.append

    add(_rule(f"PERFIL {r['user']}"))
    add(f"  {len(tl.events):,} eventos · {len(df)} días completos "
        f"· {len(tl.intervals)} tramos de pantalla")
    add(f"  tutor asignado: {'sí' if r['has_guardian'] else 'no'}")
    if tl.anomalies:
        for k, v in tl.anomalies.items():
            add(f"  anomalía: {k} ×{v}")
    add("")

    add(_rule("MEDIAS DEL PERIODO"))
    for label, value in [
        ("pantalla al día", _hm(df.screen_min.mean())),
        ("offline en vigilia", f"{df.offline_wake_h.mean():.1f} h"),
        ("desbloqueos reales", f"{df.pickups.mean():.1f}"),
        ("vistazos sin abrir", f"{df.glances.mean():.1f}"),
        ("madrugada por noche", f"{df.night_min.mean():.1f} min"),
        ("desconexión más larga", f"{df.longest_offline_s.mean()/3600:.1f} h"),
        ("mejor racha del periodo",
         f"{df.longest_offline_h.max():.1f} h "
         f"{df.loc[df.longest_offline_h.idxmax(), 'longest_offline_when']}"),
        ("apps distintas", f"{df.distinct_apps.mean():.1f}"),
        ("cambios de app por hora", f"{df.switches_per_screen_hour.mean():.1f}"),
        ("cuota de distracción", f"{df.distract_share.mean()*100:.1f} %"),
        ("bloqueos al día", f"{df.blocks.mean():.1f}"),
        ("intentos sensibles (total)", f"{int(df.blocks_sensitive.sum())}"),
        ("índice de bienestar", f"{df.score.mean():.1f} / 100"),
    ]:
        add(f"  {label:<28} {value:>12}")
    add("")

    add(_rule("POR SEMANA"))
    add(f"  {'sem':<5}{'días':>5}{'pantalla':>10}{'desbl.':>8}"
        f"{'noche':>8}{'bloq/d':>8}{'índice':>8}")
    for i, row in w.iterrows():
        marca = " *" if row["is_partial"] else "  "
        add(f"  S{i:<4}{int(row['days']):>5}{row['screen_min']:>9.0f}m"
            f"{row['pickups']:>8.0f}{row['night_min']:>7.0f}m"
            f"{row['blocks']:>8.1f}{row['score']:>8.0f}{marca}")
    add("  * semana incompleta: no genera refuerzos ni entra en comparaciones")
    add("")

    add(_rule("AVISOS AL TUTOR"))
    if not r["has_guardian"]:
        add("  perfil sin tutor: las reglas se evalúan, no hay destinatario")
    elif not r["alerts"]:
        add("  ninguna regla activada en el periodo")
    for s in r["alerts"]:
        add(f"  [{s.decision:<10}] {s.day}  {s.key}  prioridad {s.priority:.2f}")
        add(f"               {s.headline}")
        if s.decision == "enviada":
            add(f"               «{s.guardian_text}»")
            add(f"               activa {s.days_true} días, hasta {s.until}")
        else:
            add(f"               motivo: {s.reason}")
    add("")

    add(_rule("REFUERZOS"))
    if not r["positives"]:
        add("  ninguno en el periodo")
    for s in r["positives"]:
        dest = "usuario" if s.audience == "usuario" else "tutor"
        add(f"  [{s.decision:<10}] {s.day}  {s.key} → {dest}")
        add(f"               «{s.guardian_text}»")
    add("")

    add(_rule("NUDGE NOCTURNO (replay sobre el historial)"))
    ns = r["nudge_summary"]
    add(f"  noches evaluadas            {ns['noches']:>12}")
    add(f"  noches con aviso            "
        f"{ns['noches con aviso']:>7} ({ns['tasa de aparición']*100:.0f} %)")
    add(f"  min nocturnos del periodo   {ns['min nocturnos totales']:>12.0f}")
    add(f"  min posteriores al aviso    "
        f"{ns['min en juego tras el aviso']:>7.0f} "
        f"({ns['cuota del total nocturno']*100:.0f} %)")
    add(f"  por noche con aviso         "
        f"{ns['min en juego por noche con aviso']:>9.0f} min")
    add("")

    add(_rule("RESUMEN QUE SALDRÍA DEL DISPOSITIVO"))
    if r["has_guardian"]:
        for k, v in r["digest"].items():
            add(f"  {k:<28} {v:>24}")
    else:
        add("  perfil sin tutor: no sale nada del dispositivo")
    add("")

    add(_rule("EMISIONES DEL PERIODO"))
    em = r["emissions"]
    if not em:
        add("  el teléfono no emitió nada")
    for e in em:
        add(f"  {e['day']}  {e['destino']:<24} {e['detalle'][:44]}")
    add(f"  total: {len(em)} salidas en {len(df)} días")
    add("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Salida en JSON
# ---------------------------------------------------------------------------

def _plain(obj):
    """Convierte a tipos serializables sin perder precisión por el camino."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_plain(v) for v in obj]
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "item"):          # escalares de numpy
        return obj.item()
    return obj


def render_json(r: dict) -> dict:
    df, w = r["daily"], r["weekly"]
    return _plain({
        "user": r["user"],
        "has_guardian": r["has_guardian"],
        "days": len(df),
        "anomalies": dict(r["timeline"].anomalies),
        "averages": {
            "screen_min": df.screen_min.mean(),
            "offline_wake_h": df.offline_wake_h.mean(),
            "pickups": df.pickups.mean(),
            "glances": df.glances.mean(),
            "night_min": df.night_min.mean(),
            "longest_offline_h": df.longest_offline_s.mean() / 3600,
            "best_offline_h": df.longest_offline_h.max(),
            "best_offline_when": df.loc[df.longest_offline_h.idxmax(),
                                        "longest_offline_when"],
            "distinct_apps": df.distinct_apps.mean(),
            "distract_share": df.distract_share.mean(),
            "blocks": df.blocks.mean(),
            "score": df.score.mean(),
        },
        "weekly": [
            {"week": int(i), "days": int(row["days"]),
             "screen_min": row["screen_min"], "pickups": row["pickups"],
             "night_min": row["night_min"], "blocks": row["blocks"],
             "score": row["score"], "is_partial": bool(row["is_partial"])}
            for i, row in w.iterrows()
        ],
        "alerts": [
            {"key": s.key, "day": s.day, "until": s.until,
             "decision": s.decision, "priority": s.priority,
             "audience": s.audience, "tone": s.tone,
             "headline": s.headline, "text": s.guardian_text,
             "reason": s.reason, "evidence": s.evidence}
            for s in r["alerts"]
        ],
        "positives": [
            {"key": s.key, "day": s.day, "decision": s.decision,
             "audience": s.audience, "headline": s.headline,
             "text": s.guardian_text, "evidence": s.evidence}
            for s in r["positives"]
        ],
        "nudge": r["nudge_summary"],
        "guardian_digest": r["digest"] if r["has_guardian"] else None,
        "emissions": r["emissions"],
    })


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m balance.run",
        description="Deriva métricas, índice, avisos y nudges desde el log de "
                    "eventos de un dispositivo.")
    ap.add_argument("--user", choices=[*PROFILES, "all"], default="all",
                    help="perfil a analizar (por defecto, todos)")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--csv", metavar="DIR", type=Path,
                    help="además, vuelca los frames diario y semanal a CSV")
    ap.add_argument("--root", type=Path, default=Path.cwd(),
                    help="directorio donde está data/ (por defecto, el actual)")
    args = ap.parse_args(argv)

    users = list(PROFILES) if args.user == "all" else [args.user]
    salidas = []
    for u in users:
        r = analyse(u, args.root)
        salidas.append(r)
        if args.csv:
            args.csv.mkdir(parents=True, exist_ok=True)
            # las columnas con diccionarios dentro no van a un CSV plano
            r["daily"].drop(columns=["_cat_s", "_app_s", "_site_s"]).to_csv(
                args.csv / f"daily_{u}.csv", index=False)
            r["weekly"].to_csv(args.csv / f"weekly_{u}.csv")

    if args.format == "json":
        print(json.dumps([render_json(r) for r in salidas],
                         ensure_ascii=False, indent=2))
    else:
        print("\n".join(render_text(r) for r in salidas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
