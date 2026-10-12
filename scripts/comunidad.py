#!/usr/bin/env python3
"""Actividades del portal de la Comunidad de Madrid (comunidad.madrid).

El RSS «Últimas actividades» solo trae las 20 últimas publicadas y sin fechas
estructuradas, así que:

1. se lee el RSS para descubrir fichas nuevas,
2. se descarga cada ficha y se extraen fecha, hora, lugar, municipio y precio
   del bloque «Información práctica»,
3. se acumulan en una caché (data/comunidad.json) que crece día a día y
   pierde las actividades ya pasadas.

Uso suelto, para comprobar el parser contra la web real sin escribir nada:
    python scripts/comunidad.py --limit 5
"""
from __future__ import annotations

import hashlib
import html as htmllib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from typing import Callable

import agenda

RSS_URL = "https://www.comunidad.madrid/rss/latest-events.xml"
SOURCE = "cam"

MONTHS = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7,
          "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
DATE_RE = re.compile(r"(\d{1,2})\s+(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z]*\.?\s+(\d{4})")
TIME_RE = re.compile(r"\b(\d{1,2})[:.](\d{2})\b")
POSTAL_RE = re.compile(r"\b28\d{3}\s+([^,\n]+)")
FREE_RE = re.compile(r"^(gratuit|gratis|entrada libre|acceso libre|entrada gratuita)")
PRICE_RE = re.compile(r"^(entradas?|precios?)\b\s*:?\s*\S")
KIDS_RE = re.compile(r"nin[oa]s|chicos y chicas|famili|infantil|bebes|a partir de \d+ anos")
STOP_LABELS = {"ubicacion", "informacion practica", "fechas y horarios", "tipo", "compartir",
               "ver en el mapa", "como llegar", "pertenece a"}


# --------------------------------------------------------------------- RSS

def parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "").strip()
        if link:
            items.append({"title": htmllib.unescape(title), "link": link})
    return items


# ------------------------------------------------------------------- ficha

def html_to_lines(html: str) -> list[str]:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)\b[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</?(p|div|li|ul|h[1-6]|dt|dd|section|article|header|footer|tr|td|time|span|a|strong|label)\b[^>]*>", "\n", html)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", html))
    return [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines() if ln.strip()]


def _key(line: str) -> str:
    return agenda.norm(line).strip().rstrip(":").strip()


def _block_after(lines: list[str], label: str, size: int = 8) -> list[str]:
    for i, ln in enumerate(lines):
        if _key(ln) == label:
            out = []
            for nxt in lines[i + 1:i + 1 + size]:
                if _key(nxt) in STOP_LABELS:
                    break
                out.append(nxt)
            return out
    return []


def _meta(html: str, name: str) -> str:
    for pat in (rf'<meta[^>]+(?:property|name)="{name}"[^>]+content="([^"]*)"',
                rf'<meta[^>]+content="([^"]*)"[^>]+(?:property|name)="{name}"'):
        m = re.search(pat, html, re.I)
        if m:
            return htmllib.unescape(m[1]).strip()
    return ""


def _dates(line: str) -> list[str]:
    out = []
    for d, mon, y in DATE_RE.findall(agenda.norm(line)):
        try:
            out.append(date(int(y), MONTHS[mon[:3]], int(d)).isoformat())
        except ValueError:
            continue
    return out


def _location(block: list[str]) -> tuple[str, str, str, str]:
    """(lugar, dirección, distrito, municipio). Municipio vacío = Madrid capital."""
    lines = [ln for ln in block if ln not in {".", ","}]
    venue = lines[0] if lines else ""
    rest = lines[1:]
    parts = (re.sub(r"(?i)^direcci[oó]n:\s*", "", ln) for ln in rest
             if not re.match(r"(?i)^distrito\b", ln) and _key(ln) != "madrid")
    address = ", ".join(x for x in parts if x)
    district = ""
    for ln in rest:
        m = re.match(r"(?i)^distrito\s+(.+?)\.?$", ln)
        if m:
            district = agenda.district_from(m[1])
    district = district or agenda.district_in_parens(venue)
    town = ""
    m = POSTAL_RE.search(" ".join(rest))
    if m:
        town = m[1].strip()
    if agenda.norm(town) == "madrid" or district or any(_key(ln) == "madrid" for ln in rest):
        town = ""
    elif not town:
        town = "Comunidad de Madrid"
    return venue, address, district, town


def parse_event_page(html: str, url: str, title: str = "") -> list[dict]:
    """Una actividad por sesión (o una con rango si la línea trae dos fechas)."""
    lines = html_to_lines(html)
    title = title or _meta(html, "og:title")
    ref = re.search(r"Ref:\s*#?\s*(\d{5,})", "\n".join(lines))
    base_id = f"{SOURCE}-{ref[1]}" if ref else f"{SOURCE}-{hashlib.sha1(url.encode()).hexdigest()[:10]}"
    tipo = (_block_after(lines, "tipo", 1) or [""])[0]
    sessions = [ln for ln in _block_after(lines, "fechas y horarios", 12) if _dates(ln)]
    if not sessions:
        return []
    venue, address, district, town = _location(_block_after(lines, "ubicacion", 6))

    # Precio y público van tras la descripción; se buscan solo cerca de la
    # ficha para no confundirlos con los menús del portal.
    start = next((i for i, ln in enumerate(lines) if _key(ln) == "informacion practica"), 0)
    free, price, kids_line = False, "", ""
    for ln in lines[start:start + 80]:
        k = agenda.norm(ln)
        if not free and FREE_RE.match(k):
            free = True
        if not price and PRICE_RE.match(k) and len(ln) < 160:
            price = ln
        if not kids_line and KIDS_RE.search(k) and 15 <= len(ln) < 160:
            kids_line = ln
    if not price and free:
        price = "Gratuita"

    desc = _meta(html, "og:description") or _meta(html, "description")
    coords = re.search(r"(40\.\d{3,})\s*[,/]\s*(-[34]\.\d{3,})", html)
    out = []
    for n, ln in enumerate(sessions):
        ds = _dates(ln)
        times = TIME_RE.findall(ln)
        ev = agenda.make_event(
            id=base_id if len(sessions) == 1 else f"{base_id}-{n + 1}",
            title=title, type_=tipo, start=min(ds), end=max(ds),
            time=f"{int(times[0][0]):02d}:{times[0][1]}" if times else "",
            desc=desc, price=price, free=free, venue=venue,
            district=district, lat=coords[1] if coords else None,
            lng=coords[2] if coords else None, link=url, audience=kids_line,
        )
        ev["kids"] = ev["kids"] or bool(kids_line)
        if town:
            ev["district"] = ""
        ev["town"] = town
        ev["address"] = address
        ev["source"] = SOURCE
        out.append(ev)
    return out


# ------------------------------------------------------------------- caché

def load_cache(path: Path) -> dict[str, dict]:
    try:
        return {e["id"]: e for e in json.loads(path.read_text(encoding="utf-8"))["events"]}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def save_cache(path: Path, events: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"events": sorted(events.values(), key=lambda e: (e["start"], e["id"]))}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def update(cache_path: Path, today: date, fetch: Callable[[str], bytes],
           pause: float = 1.0, limit: int | None = None) -> list[dict]:
    """Lee el RSS, refresca sus fichas, purga lo pasado y devuelve la caché vigente."""
    cache = load_cache(cache_path)
    items = parse_rss(fetch(RSS_URL))[:limit]
    fresh = 0
    for it in items:
        try:
            evs = parse_event_page(agenda.decode(fetch(it["link"])), it["link"], it["title"])
        except Exception as e:  # noqa: BLE001 - una ficha rota no tumba el resto
            print(f"  ficha descartada {it['link']}: {e}", file=sys.stderr)
            continue
        for old in [k for k, v in cache.items() if v.get("link") == it["link"]]:
            del cache[old]
        for ev in evs:
            cache[ev["id"]] = ev
            fresh += 1
        time.sleep(pause)
    today_key = today.isoformat()
    cache = {k: v for k, v in cache.items() if v["end"] >= today_key}
    save_cache(cache_path, cache)
    print(f"  Comunidad: {len(items)} fichas en el RSS, {fresh} sesiones leídas, {len(cache)} vigentes en caché")
    return list(cache.values())


if __name__ == "__main__":
    import argparse
    import tempfile
    import fetch_agenda

    ap = argparse.ArgumentParser(description="Prueba el parser contra la web real (no escribe nada).")
    ap.add_argument("--limit", type=int, default=5)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        evs = update(Path(tmp) / "c.json", date.today(), fetch_agenda.download, limit=a.limit)
    for e in evs:
        print(json.dumps({k: e[k] for k in ("title", "cat", "start", "end", "time", "venue",
                                            "district", "town", "free", "price", "kids")},
                         ensure_ascii=False))
