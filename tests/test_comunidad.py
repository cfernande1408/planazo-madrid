import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import comunidad  # noqa: E402
import fetch_agenda  # noqa: E402
import test_agenda  # noqa: E402
from unittest import mock  # noqa: E402

# Fichas reducidas a la estructura que muestra comunidad.madrid (Drupal):
# etiquetas y valores en elementos separados, menú con «Familias».
NAV = '<nav><ul><li><a href="/familia">Familias</a></li><li><a href="/cultura">Cultura</a></li></ul></nav>'

GETAFE_NEGRO = f"""<html><head><title>x</title>
<meta property="og:title" content="Getafe Negro 2026. Parecía una persona normal">
<meta property="og:description" content="Un breve recorrido por la narrativa negra contemporánea.">
</head><body>{NAV}
<h1>Getafe Negro 2026. Parecía una persona normal</h1>
<div class="field"><span>Tipo:</span> <span>Taller</span></div>
<div>Ref: #</div><div>11023215</div>
<h2>Información práctica</h2>
<p>Próximamente apertura del plazo de inscripción</p>
<h3>Fechas y horarios</h3>
<div><time>Viernes, 23 Oct 2026 | 12:00 - 13:30</time></div>
<h3>Ubicación</h3>
<div><a>Biblioteca Pública Pedro Salinas (Centro)</a></div>
<div><strong>Dirección:</strong> Glorieta Puerta de Toledo, 1</div><div>.</div>
<div>Distrito Centro.</div><div>Madrid</div>
<a href="https://maps.google.com/?q=40.4065,-3.7110">Ver en el mapa</a>
<p>Jóvenes y adultos</p>
</body></html>"""

RELATED = """<h2>Etiquetas</h2><a>Agenda cultural</a>
<h2>También te puede interesar</h2>
<div><a>Taller monográfico familiar: ALAS Y SUSURROS II</a><span>Educativa/Curso</span><time>Sábado, 17 Oct 2026 | 12:00</time></div>
<footer><a>BOCM</a><a>RSS</a></footer>"""

LA_CABRERA = f"""<html><head>
<meta content="Acuarela experimental para jóvenes." property="og:description">
</head><body>{NAV}
<p>Sábado 28 noviembre, 10.00 a 12.30 h</p>
<div>Tipo:</div><div>Educativa/Curso</div>
<div>Ref: # 11023240</div>
<h2>Información práctica</h2>
<h3>Fechas y horarios</h3>
<div><time>Sábado, 28 Nov 2026 | 10:00</time><span>-</span><time>12:30</time></div>
<h3>Ubicación</h3>
<div>Centro Comarcal de Humanidades Sierra Norte</div>
<div>Av. de la Cabrera, 96, 28751 La Cabrera, Madrid, España</div>
<div>Transporte público disponible, autobuses interurbanos:</div>
<div>líneas números</div><div>191</div><div>Madrid (Plaza Castilla) - Buitrago,</div>
<a>Ver en el mapa</a>
<p>Sábado 28 noviembre, 10.00 a 12.30 h</p>
<p>¿Y si la hoja en blanco dejara de dar miedo?</p>
<p>Actividad pública para chicos y chicas a partir de 10 años (adulto acompañante opcional). Gratuita.</p>
<h3>Dirigido a</h3><p>Actividad pública para chicos y chicas a partir de 10 años (adulto acompañante opcional)</p>
{RELATED}
</body></html>"""

VOLUNTARIADO = f"""<html><body>{NAV}
<div>Tipo:</div><div>Curso</div><div>Ref: # 11023300</div>
<h2>Información práctica</h2>
<h3>Fechas y horarios</h3>
<div>Lunes, 16 Nov 2026 | 17:00</div><div>-</div><div>20:00</div>
<div>Miércoles, 18 Nov 2026 | 17:00</div><div>-</div><div>20:00</div>
<h3>Ubicación</h3>
<div>Centro de Voluntariado</div><div>Plaza del Ayuntamiento, 1, 28760 Tres Cantos, Madrid</div>
<p>Entrada: 2 euros en taquilla</p>
</body></html>"""

EXPO = f"""<html><body>{NAV}
<div>Tipo:</div><div>Exposición</div><div>Ref: # 11023400</div>
<h2>Información práctica</h2>
<h3>Fechas y horarios</h3>
<div><time>Viernes, 20 Nov 2026 | 10:00</time><span>-</span><time>Viernes, 22 Ene 2027 | 21:30</time></div>
<h3>Ubicación</h3>
<div>CCHSN</div><div>Av. de la Cabrera, 96, 28751 La Cabrera, Madrid, España</div>
<div>CCHSN</div><div>Av. de la Cabrera, 96, 28751 La Cabrera, Madrid, España</div>
<h4>Cómo llegar:</h4><div>Transporte público disponible</div>
<a>Ver en el mapa</a>
<p>Las obras recuerdan juegos de niños y la infancia perdida.</p>
<p>Entrada: 3 euros, reducida 1,50 €</p>
{RELATED}
</body></html>"""

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><title>x</title>
<item><title>Getafe Negro 2026. Parec&#xED;a una persona normal</title><link>https://www.comunidad.madrid/actividades/2026/getafe</link><pubDate>Fri, 09 Oct 2026 05:34:30 +0000</pubDate></item>
<item><title>Trazos de agua</title><link>https://www.comunidad.madrid/actividades/2026/cabrera</link></item>
<item><title>Ficha rota</title><link>https://www.comunidad.madrid/actividades/2026/rota</link></item>
</channel></rss>"""


class PageTest(unittest.TestCase):
    def test_capital_event(self):
        [ev] = comunidad.parse_event_page(GETAFE_NEGRO, "https://x/getafe")
        self.assertEqual(ev["id"], "cam-11023215")
        self.assertEqual(ev["title"], "Getafe Negro 2026. Parecía una persona normal")
        self.assertEqual((ev["start"], ev["end"], ev["time"]), ("2026-10-23", "2026-10-23", "12:00"))
        self.assertEqual(ev["cat"], "talleres")
        self.assertEqual(ev["venue"], "Biblioteca Pública Pedro Salinas (Centro)")
        self.assertEqual(ev["district"], "Centro")
        self.assertEqual(ev["town"], "")
        self.assertEqual(ev["address"], "Glorieta Puerta de Toledo, 1")
        self.assertEqual((ev["lat"], ev["lng"]), (40.4065, -3.711))
        self.assertEqual(ev["desc"], "Un breve recorrido por la narrativa negra contemporánea.")
        self.assertFalse(ev["kids"], "el menú «Familias» no debe contar")
        self.assertEqual(ev["source"], "cam")

    def test_other_town_free_and_kids(self):
        [ev] = comunidad.parse_event_page(LA_CABRERA, "https://x/cabrera", "Trazos de agua")
        self.assertEqual(ev["id"], "cam-11023240")
        self.assertEqual(ev["town"], "La Cabrera")
        self.assertEqual(ev["district"], "")
        self.assertEqual((ev["start"], ev["end"], ev["time"]), ("2026-11-28", "2026-11-28", "10:00"))
        self.assertEqual(ev["address"], "Av. de la Cabrera, 96, 28751 La Cabrera, Madrid")
        self.assertEqual(ev["audience"], "Actividad pública para chicos y chicas a partir de 10 años (adulto acompañante opcional)")
        self.assertTrue(ev["free"])
        self.assertEqual(ev["price"], "Gratuita")
        self.assertTrue(ev["kids"])
        self.assertEqual(ev["cat"], "talleres")

    def test_one_event_per_session(self):
        evs = comunidad.parse_event_page(VOLUNTARIADO, "https://x/v", "Habilidades sociales")
        self.assertEqual([e["id"] for e in evs], ["cam-11023300-1", "cam-11023300-2"])
        self.assertEqual([e["start"] for e in evs], ["2026-11-16", "2026-11-18"])
        self.assertEqual(evs[0]["town"], "Tres Cantos")
        self.assertEqual([e["end"] for e in evs], ["2026-11-16", "2026-11-18"])
        self.assertEqual(evs[0]["time"], "17:00")
        self.assertEqual(evs[0]["price"], "Entrada: 2 euros en taquilla")
        self.assertFalse(evs[0]["free"])

    def test_range_with_end_on_its_own_line(self):
        [ev] = comunidad.parse_event_page(EXPO, "https://x/e", "Atravesar mi piel")
        self.assertEqual((ev["start"], ev["end"], ev["time"]), ("2026-11-20", "2027-01-22", "10:00"))
        self.assertEqual(ev["cat"], "expos")
        self.assertEqual(ev["venue"], "CCHSN")
        self.assertEqual(ev["address"], "Av. de la Cabrera, 96, 28751 La Cabrera, Madrid")
        self.assertEqual(ev["town"], "La Cabrera")
        self.assertFalse(ev["kids"], "ni la descripción ni los relacionados cuentan")
        self.assertFalse(ev["free"])
        self.assertEqual(ev["price"], "Entrada: 3 euros, reducida 1,50 €")
        self.assertEqual(ev["eur"], 3.0)

    def test_single_line_range(self):
        html = EXPO.replace("<time>Viernes, 20 Nov 2026 | 10:00</time><span>-</span><time>Viernes, 22 Ene 2027 | 21:30</time>",
                            "Del Martes, 06 Oct 2026 al Domingo, 20 Dic 2026 | 11:00 - 20:00")
        [ev] = comunidad.parse_event_page(html, "u", "x")
        self.assertEqual((ev["start"], ev["end"], ev["time"]), ("2026-10-06", "2026-12-20", "11:00"))

    def test_page_without_dates_is_skipped(self):
        self.assertEqual(comunidad.parse_event_page("<html><body>Nada</body></html>", "u"), [])


class CacheTest(unittest.TestCase):
    PAGES = {
        comunidad.RSS_URL: RSS,
        "https://www.comunidad.madrid/actividades/2026/getafe": GETAFE_NEGRO.encode(),
        "https://www.comunidad.madrid/actividades/2026/cabrera": LA_CABRERA.encode(),
    }

    def fetch(self, url):
        if url not in self.PAGES:
            raise OSError("404")
        return self.PAGES[url]

    def test_rss(self):
        items = comunidad.parse_rss(RSS)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["title"], "Getafe Negro 2026. Parecía una persona normal")

    def test_update_accumulates_and_purges(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            old = {"id": "cam-1", "title": "Antigua pero vigente", "start": "2026-10-20", "end": "2026-10-20",
                   "link": "https://x/antigua"}
            past = {"id": "cam-2", "title": "Ya pasó", "start": "2026-10-01", "end": "2026-10-02",
                    "link": "https://x/pasada"}
            path.write_text(json.dumps({"events": [old, past]}), encoding="utf-8")
            evs = comunidad.update(path, date(2026, 10, 13), self.fetch, pause=0)
            ids = sorted(e["id"] for e in evs)
            self.assertEqual(ids, ["cam-1", "cam-11023215", "cam-11023240"])
            self.assertEqual(sorted(e["id"] for e in comunidad.load_cache(path).values()), ids)

    def test_update_replaces_changed_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "c.json"
            comunidad.update(path, date(2026, 10, 13), self.fetch, pause=0)
            self.PAGES = dict(self.PAGES)
            self.PAGES["https://www.comunidad.madrid/actividades/2026/getafe"] = \
                GETAFE_NEGRO.replace("12:00 - 13:30", "18:00 - 19:30").encode()
            evs = {e["id"]: e for e in comunidad.update(path, date(2026, 10, 13), self.fetch, pause=0)}
            self.assertEqual(evs["cam-11023215"]["time"], "18:00")



class CliTest(unittest.TestCase):
    def test_both_sources_end_to_end(self):
        pages = dict(CacheTest.PAGES)
        pages[fetch_agenda.SOURCES[0]] = test_agenda.CSV_TEXT.encode("cp1252")

        def fake_download(url):
            if url not in pages:
                raise OSError("404")
            return pages[url]

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fetch_agenda, "download", fake_download), \
                mock.patch.object(comunidad.time, "sleep"):
            out, cache = Path(tmp) / "agenda.json", Path(tmp) / "cam.json"
            code = fetch_agenda.main(["--out", str(out), "--comunidad-cache", str(cache),
                                      "--min-events", "1", "--today", "2026-10-13"])
            self.assertEqual(code, 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["sources"]["cam"], 2)
            self.assertEqual({e["source"] for e in payload["events"]}, {"ayto", "cam"})
            self.assertTrue(all("town" in e for e in payload["events"]))
            self.assertTrue(cache.exists())

    def test_comunidad_down_uses_cache(self):
        def fake_download(url):
            if url == fetch_agenda.SOURCES[0]:
                return test_agenda.CSV_TEXT.encode()
            raise OSError("caída")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fetch_agenda, "download", fake_download):
            out, cache = Path(tmp) / "agenda.json", Path(tmp) / "cam.json"
            cached = {"id": "cam-9", "title": "En caché", "start": "2026-10-20", "end": "2026-10-20",
                      "time": "", "source": "cam", "town": ""}
            cache.write_text(json.dumps({"events": [cached]}), encoding="utf-8")
            self.assertEqual(fetch_agenda.main(["--out", str(out), "--comunidad-cache", str(cache),
                                                "--min-events", "1", "--today", "2026-10-13"]), 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("cam-9", [e["id"] for e in payload["events"]])


if __name__ == "__main__":
    unittest.main()
