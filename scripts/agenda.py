"""Normaliza la agenda de actividades del Ayuntamiento de Madrid al formato de la app.

Acepta los dos formatos que ha publicado el portal de datos abiertos:

* CSV del dataset 300107-0 «Agenda de actividades y eventos» (portal actual).
* JSON-LD del dataset 206974-0 «Actividades culturales y de ocio en los
  próximos 100 días» (portal antiguo, ``@graph``).

Cada actividad se convierte en un dict con las claves que espera
``site/index.html``: id, title, desc, cat, kids, free, price, start, end,
time, days, excl, venue, district, lat, lng, link, audience y, si procede,
longHint.
"""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import date

CATEGORIES: list[tuple[str, tuple[str, ...]]] = [
    ("musica", ("musica", "concierto", "jazz", "flamenco", "rock", "coro", "orquesta")),
    ("escena", ("teatro", "danza", "baile", "performance", "circo", "magia", "escenic")),
    ("cine", ("cine", "audiovisual", "proyecci", "cortometraje")),
    ("expos", ("exposic", "muestra")),
    ("letras", ("conferenc", "coloqu", "recital", "literar", "lectura", "presentaci",
                "debate", "poesia", "libro")),
    ("talleres", ("taller", "curso", "formaci")),
    ("peques", ("cuentacuento", "titere", "marioneta", "infantil", "familia", "ninos")),
    ("calle", ("calle", "urbano", "fiesta", "feria", "mercad", "verbena", "carnaval",
               "navidad", "cabalgata")),
    ("deporte", ("deport", "carrera", "yoga", "marcha", "bici")),
    ("rutas", ("excursion", "itinerario", "visita", "ruta", "paseo")),
]

DISTRICTS = {
    "centro": "Centro", "arganzuela": "Arganzuela", "retiro": "Retiro",
    "salamanca": "Salamanca", "chamartin": "Chamartín", "tetuan": "Tetuán",
    "chamberi": "Chamberí", "fuencarralelpardo": "Fuencarral-El Pardo",
    "moncloaaravaca": "Moncloa-Aravaca", "latina": "Latina",
    "carabanchel": "Carabanchel", "usera": "Usera",
    "puentedevallecas": "Puente de Vallecas", "moratalaz": "Moratalaz",
    "ciudadlineal": "Ciudad Lineal", "hortaleza": "Hortaleza",
    "villaverde": "Villaverde", "villadevallecas": "Villa de Vallecas",
    "vicalvaro": "Vicálvaro", "sanblascanillejas": "San Blas-Canillejas",
    "barajas": "Barajas",
}

# 0 = domingo, como Date.getDay() en JavaScript.
WEEKDAYS = {
    "MO": 1, "TU": 2, "WE": 3, "TH": 4, "FR": 5, "SA": 6, "SU": 0,
    "L": 1, "M": 2, "X": 3, "J": 4, "V": 5, "S": 6, "D": 0,
    "LUNES": 1, "MARTES": 2, "MIERCOLES": 3, "JUEVES": 4, "VIERNES": 5,
    "SABADO": 6, "DOMINGO": 0,
}

TRUTHY = {"1", "si", "s", "true", "yes", "y"}
DESC_MAX = 900


def norm(text: object) -> str:
    """Minúsculas y sin tildes."""
    s = unicodedata.normalize("NFD", str(text or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def last_segment(value: object) -> str:
    parts = [p for p in str(value or "").split("/") if p]
    return parts[-1] if parts else ""


def classify(type_: str, title: str, desc: str = "") -> str:
    """Categoría a partir del tipo oficial; si no basta, del título y la descripción.

    Muchas actividades llegan como «ProgramacionDestacadaAgendaCultura» con
    el nombre del artista por título, así que la descripción decide.
    """
    t = str(type_ or "")
    t = norm(t.split("/actividades/", 1)[1] if "/actividades/" in t else last_segment(t))
    for text in (t, norm(title), norm(desc)[:400]):
        for cat, keywords in CATEGORIES:
            if any(k in text for k in keywords):
                return cat
    return "otros"


def district_from(value: object) -> str:
    """Nombre de distrito a partir de texto libre o de la URI del portal."""
    key = re.sub(r"[^a-z]", "", norm(last_segment(value) if "/" in str(value or "") else value))
    return DISTRICTS.get(key, "")


# Nombres extra que aparecen en títulos y lugares.
DISTRICT_ALIASES = {
    "san blas": "San Blas-Canillejas", "fuencarral": "Fuencarral-El Pardo",
    "moncloa": "Moncloa-Aravaca", "aravaca": "Moncloa-Aravaca",
}
# Palabras corrientes que solo cuentan como distrito con contexto explícito.
AMBIGUOUS_DISTRICTS = {"centro", "latina", "retiro", "salamanca"}


def _text_key(value: object) -> str:
    s = re.sub(r"[-–—]", " ", norm(value))
    return re.sub(r"\s+", " ", s).strip()


_DISTRICT_TEXT = sorted(
    [(_text_key(name), name) for name in DISTRICTS.values()]
    + [(_text_key(k), v) for k, v in DISTRICT_ALIASES.items()],
    key=lambda kv: -len(kv[0]),
)


def district_in_text(*texts: object) -> str:
    """Distrito mencionado en un título o lugar: «(Fuencarral-El Pardo)», «- Chamartin»."""
    s = _text_key(" ".join(str(t or "") for t in texts))
    for key, name in _DISTRICT_TEXT:
        if key in AMBIGUOUS_DISTRICTS:
            pattern = rf"(distrito (de )?{key}\b|\({key}\))"
        else:
            pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, s):
            return name
    return ""


def clean_audience(value: object) -> str:
    """«/usuario/Niños,/usuario/PoblaciónGeneral» → «Niños, Población general»."""
    parts: list[str] = []
    for raw in re.split(r"[,;]", str(value or "")):
        seg = last_segment(raw.strip()) if "/" in raw else raw.strip()
        seg = re.sub(r"(?<=[a-zñáéíóú])(?=[A-ZÑÁÉÍÓÚ])", " ", seg).strip()
        if seg:
            parts.append(seg[0].upper() + seg[1:].lower())
    return ", ".join(dict.fromkeys(parts))


def parse_weekdays(value: object) -> list[int] | None:
    tokens = re.split(r"[,;\s/]+", norm(value).upper())
    days = sorted({WEEKDAYS[t] for t in tokens if t in WEEKDAYS})
    return days or None


def date_keys(value: object) -> list[str]:
    """Todas las fechas de un texto, como YYYY-MM-DD, en orden de aparición."""
    s = str(value or "")
    found: list[tuple[int, str]] = []
    for m in re.finditer(r"(\d{4})-(\d{2})-(\d{2})", s):
        found.append((m.start(), f"{m[1]}-{m[2]}-{m[3]}"))
    for m in re.finditer(r"(\d{1,2})/(\d{1,2})/(\d{4})", s):
        found.append((m.start(), f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"))
    return [k for _, k in sorted(found)]


def date_key(value: object) -> str:
    keys = date_keys(value)
    return keys[0] if keys else ""


def clean_time(value: object) -> str:
    m = re.search(r"(\d{1,2}):(\d{2})", str(value or ""))
    return f"{int(m[1]):02d}:{m[2]}" if m else ""


def clean_text(value: object, limit: int | None = None) -> str:
    s = re.sub(r"<[^>]+>", " ", str(value or ""))
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s).strip()
    return s[:limit].rstrip() if limit and len(s) > limit else s


def coord(value: object) -> float | None:
    try:
        x = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None
    if x != x or x == 0:  # NaN o vacío
        return None
    return round(x, 6)


def truthy(value: object) -> bool:
    return norm(value).strip() in TRUTHY or value is True


def make_event(*, id: str, title: str, type_: str, start: str, end: str, time: str,
               desc: str = "", price: str = "", free: bool = False,
               days: list[int] | None = None, excl: list[str] | None = None,
               venue: str = "", district: str = "", lat=None, lng=None,
               link: str = "", audience: str = "", long_hint: bool = False) -> dict:
    title = clean_text(title)
    desc = clean_text(desc, DESC_MAX)
    cat = classify(type_, title, desc)
    audience = clean_audience(clean_text(audience))
    venue = clean_text(venue)
    district = district or district_in_text(title, venue)
    ev = {
        "id": str(id),
        "title": title,
        "desc": desc,
        "cat": cat,
        "kids": cat == "peques" or bool(re.search(r"nin|famil|infan|bebe", norm(audience))),
        "free": bool(free),
        "price": clean_text(price, 120),
        "start": start,
        "end": end if end >= start else start,
        "time": time,
        "days": days,
        "excl": excl or [],
        "venue": venue,
        "district": district,
        "lat": coord(lat),
        "lng": coord(lng),
        "link": str(link or "").strip(),
        "audience": audience,
    }
    # Larga duración abierta casi a diario (exposiciones): la app la muestra
    # aparte. Con 1-4 días por semana es un ciclo de sesiones y va a su día.
    if long_hint and (not days or len(days) >= 5):
        ev["longHint"] = True
    return ev


# ---------------------------------------------------------------- CSV (300107-0)

def read_csv(text: str) -> list[dict]:
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    return [{(k or "").strip().lstrip("﻿").upper(): (v or "") for k, v in row.items()}
            for row in reader]


def from_csv_row(row: dict) -> dict | None:
    title = row.get("TITULO") or row.get("TITULO-ACTIVIDAD") or ""
    start = date_key(row.get("FECHA"))
    if not title.strip() or not start:
        return None
    venue = row.get("NOMBRE-INSTALACION", "")
    return make_event(
        id=row.get("ID-EVENTO") or f"{title}|{start}",
        title=title,
        type_=row.get("TIPO", ""),
        start=start,
        end=date_key(row.get("FECHA-FIN")) or start,
        time=clean_time(row.get("HORA")),
        desc=row.get("DESCRIPCION", ""),
        price=row.get("PRECIO", ""),
        free=truthy(row.get("GRATUITO")),
        days=parse_weekdays(row.get("DIAS-SEMANA")),
        excl=date_keys(row.get("DIAS-EXCLUIDOS")),
        venue=venue,
        district=district_from(row.get("DISTRITO-INSTALACION")) or district_in_parens(venue),
        lat=row.get("LATITUD"),
        lng=row.get("LONGITUD"),
        link=row.get("CONTENT-URL") or row.get("URL-ACTIVIDAD") or "",
        audience=row.get("AUDIENCIA", ""),
        long_hint=truthy(row.get("LARGA-DURACION")),
    )


# ------------------------------------------------------------ JSON-LD (206974-0)

def sanitize_json(text: str) -> str:
    """El JSON del portal trae saltos de línea y escapes inválidos dentro de cadenas."""
    text = re.sub(r"[\x00-\x1f]", " ", text.lstrip("﻿"))
    return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)


def district_in_parens(venue: str) -> str:
    m = re.search(r"\(([^)]+)\)\s*$", venue or "")
    return district_from(m[1]) if m else ""


def from_jsonld_item(it: dict) -> dict | None:
    if not isinstance(it, dict):
        return None
    title = it.get("title") or ""
    start = date_key(it.get("dtstart"))
    if not str(title).strip() or not start:
        return None
    address = it.get("address") or {}
    area = address.get("area") or {}
    venue = it.get("event-location") or area.get("street-address") or ""
    district = district_from((address.get("district") or {}).get("@id")) or district_in_parens(venue)
    rec = it.get("recurrence") or {}
    loc = it.get("location") or {}
    return make_event(
        id=it.get("id") or it.get("uid") or it.get("@id") or f"{title}|{start}",
        title=title,
        type_=it.get("@type", ""),
        start=start,
        end=date_key(it.get("dtend")) or start,
        time=clean_time(it.get("time")),
        desc=it.get("description", ""),
        price=it.get("price", ""),
        free=truthy(it.get("free")),
        days=parse_weekdays(rec.get("days")) if isinstance(rec, dict) else None,
        excl=date_keys(it.get("excluded-days")),
        venue=venue,
        district=district,
        lat=loc.get("latitude"),
        lng=loc.get("longitude"),
        link=it.get("link", ""),
        audience=it.get("audience", ""),
    )


# ------------------------------------------------------------------- pipeline

def decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def parse(text: str) -> list[dict]:
    """Detecta el formato y devuelve las actividades sin filtrar."""
    stripped = text.lstrip("﻿ \r\n\t")
    if stripped[:1] in "{[":
        data = json.loads(sanitize_json(stripped))
        items = data if isinstance(data, list) else data.get("@graph") or data.get("records") or []
        events = [from_jsonld_item(it) for it in items]
    else:
        events = [from_csv_row(row) for row in read_csv(stripped)]
    return [e for e in events if e]


def normalize(text: str, today: date) -> list[dict]:
    """Actividades que no han terminado antes de hoy, con id único, ordenadas."""
    today_key = today.isoformat()
    out: list[dict] = []
    seen: dict[str, int] = {}
    for ev in parse(text):
        if ev["end"] < today_key:
            continue
        base = ev["id"]
        n = seen.get(base, 0)
        seen[base] = n + 1
        if n:
            ev["id"] = f"{base}-{n}"
        out.append(ev)
    out.sort(key=lambda e: (e["start"], e["time"] or "99", e["title"]))
    return out


def merge(*groups: list[dict]) -> list[dict]:
    """Une fuentes por orden de preferencia, sin repetir (mismo título y día)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for group in groups:
        for ev in group:
            key = (re.sub(r"[^a-z0-9]", "", norm(ev["title"])), ev["start"])
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
    out.sort(key=lambda e: (e["start"], e["time"] or "99", e["title"]))
    return out


def to_payload(events: list[dict], source: str, generated_at: str) -> dict:
    return {"generatedAt": generated_at, "source": source, "count": len(events), "events": events}
