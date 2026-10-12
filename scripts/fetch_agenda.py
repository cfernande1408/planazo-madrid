#!/usr/bin/env python3
"""Descarga la agenda del Ayuntamiento de Madrid y escribe site/data/agenda.json.

Fuentes:
    * Ayuntamiento de Madrid (obligatoria): agenda del portal de datos abiertos.
    * Comunidad de Madrid (opcional): RSS de actividades + fichas, acumuladas
      en data/comunidad.json. Si falla, se usa lo que haya en la caché.

Uso:
    python scripts/fetch_agenda.py                  # descarga de todas las fuentes
    python scripts/fetch_agenda.py --input f.csv    # normaliza un CSV/JSON del Ayuntamiento

Sale con código 1 si el Ayuntamiento no da al menos --min-events actividades;
en ese caso no toca el fichero de salida.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import agenda
import comunidad

MADRID = ZoneInfo("Europe/Madrid")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "site" / "data" / "agenda.json"
DEFAULT_CAM_CACHE = ROOT / "data" / "comunidad.json"

SOURCES = [
    # Portal actual: dataset 300107-0 «Agenda de actividades y eventos» (CSV)
    "https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos/resource/"
    "300107-2-agenda-actividades-eventos-csv/download/300107-2-agenda-actividades-eventos-csv.csv",
    "https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos/resource/"
    "300107-2-agenda-actividades-eventos-csv/download/300107-0-agenda-actividades-eventos.csv",
    # Portal antiguo: actividades culturales y de ocio de los próximos 100 días (JSON-LD)
    "https://datos.madrid.es/egob/catalogo/206974-0-agenda-eventos-culturales-100.json",
]
USER_AGENT = "planazo-madrid/1.0 (agenda personal; +https://github.com)"


def download(url: str, attempts: int = 3, timeout: int = 90) -> bytes:
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 - reintentamos cualquier fallo de red
            last = e
            print(f"  intento {i + 1}/{attempts} falló: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"no se pudo descargar {url}: {last}")


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, help="fichero CSV o JSON ya descargado")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-events", type=int, default=50)
    ap.add_argument("--today", type=date.fromisoformat, help="fecha de corte (por defecto, hoy en Madrid)")
    ap.add_argument("--comunidad-cache", type=Path, default=DEFAULT_CAM_CACHE)
    ap.add_argument("--skip-comunidad", action="store_true",
                    help="no consultar comunidad.madrid (implícito con --input)")
    args = ap.parse_args(argv)

    now = datetime.now(MADRID)
    today = args.today or now.date()
    candidates = [(str(args.input), lambda: args.input.read_bytes())] if args.input else \
        [(url, lambda url=url: download(url)) for url in SOURCES]

    ayto = None
    for source, get in candidates:
        print(f"Probando {source}")
        try:
            events = agenda.normalize(agenda.decode(get()), today)
        except Exception as e:  # noqa: BLE001 - probamos la siguiente fuente
            print(f"  descartada: {e}", file=sys.stderr)
            continue
        print(f"  {len(events)} actividades vigentes")
        if len(events) < args.min_events:
            print(f"  descartada: menos de {args.min_events}", file=sys.stderr)
            continue
        ayto = events
        break
    if ayto is None:
        print("Ninguna fuente válida; no se modifica la agenda.", file=sys.stderr)
        return 1
    for ev in ayto:
        ev.setdefault("source", "ayto")
        ev.setdefault("town", "")

    cam: list[dict] = []
    if not (args.input or args.skip_comunidad):
        print(f"Probando {comunidad.RSS_URL}")
        try:
            cam = comunidad.update(args.comunidad_cache, today, download)
        except Exception as e:  # noqa: BLE001 - la Comunidad es opcional
            print(f"  Comunidad descartada: {e}; uso la caché", file=sys.stderr)
            cam = [e for e in comunidad.load_cache(args.comunidad_cache).values()
                   if e["end"] >= today.isoformat()]

    events = agenda.merge(ayto, cam)
    payload = agenda.to_payload(events, source, now.isoformat(timespec="seconds"))
    payload["sources"] = {"ayto": len(ayto), "cam": len(cam)}
    write_atomic(args.out, payload)
    print(f"Escrito {args.out}: {len(events)} actividades ({len(ayto)} Ayuntamiento, {len(cam)} Comunidad)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
