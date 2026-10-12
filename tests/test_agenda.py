import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import agenda  # noqa: E402
import fetch_agenda  # noqa: E402

TODAY = date(2026, 10, 12)

# Mismas columnas que el dataset 300107-0, separado por «;», con una
# descripción multilínea entre comillas y un ID-EVENTO repetido.
CSV_TEXT = (
    "ID-EVENTO;TITULO;PRECIO;GRATUITO;LARGA-DURACION;DIAS-SEMANA;DIAS-EXCLUIDOS;FECHA;FECHA-FIN;"
    "HORA;DESCRIPCION;CONTENT-URL;TITULO-ACTIVIDAD;URL-ACTIVIDAD;URL-INSTALACION;NOMBRE-INSTALACION;"
    "ACCESIBILIDAD-INSTALACION;CLASE-VIAL-INSTALACION;NOMBRE-VIA-INSTALACION;NUM-INSTALACION;"
    "DISTRITO-INSTALACION;BARRIO-INSTALACION;CODIGO-POSTAL-INSTALACION;COORDENADA-X;COORDENADA-Y;"
    "LATITUD;LONGITUD;TIPO;AUDIENCIA\n"
    '101;Concierto de otoño;;1;0;;;2026-10-14 00:00:00.0;2026-10-14 23:59:00.0;19:00;'
    '"Primera línea\nSegunda <b>línea</b>";https://www.madrid.es/ev/101;;;;'
    "Centro Cultural Lucero;;CALLE;X;1;LATINA;LUCERO;28011;;;40,4031;-3,7392;"
    "/contenido/actividades/Musica;Jóvenes\n"
    "102;Taller de cerámica;6 €;0;0;L,X;20/10/2026;2026-10-12 00:00:00.0;2026-11-30 23:59:00.0;"
    "9:30;;;;;;Centro Cultural Galileo;;;;;CHAMBERÍ;;;;;;;/contenido/actividades/CursosTalleres;\n"
    "103;Exposición de carteles;;1;1;;;2026-09-01 00:00:00.0;2026-12-31 23:59:00.0;;;;;;;"
    "Matadero Madrid;;;;;ARGANZUELA;;;;;;;/contenido/actividades/Exposiciones;\n"
    "104;Ya pasó;;1;0;;;2026-10-01 00:00:00.0;2026-10-02 00:00:00.0;18:00;;;;;;"
    "Biblioteca;;;;;RETIRO;;;;;;;/contenido/actividades/Musica;\n"
    "101;Concierto de otoño;;1;0;;;2026-10-21 00:00:00.0;2026-10-21 23:59:00.0;19:00;;;;;;"
    "Centro Cultural Lucero;;;;;LATINA;;;;;;;/contenido/actividades/Musica;\n"
    "105;Fotografía de barrio;;1;1;M,X,J,V,S,D;;2026-09-15 00:00:00.0;2026-12-15 23:59:00.0;;;;;;;"
    "Centro Cultural Conde Duque;;;;;CENTRO;;;;;;;/contenido/actividades/Exposiciones;\n"
    "106;Club de ajedrez;;1;1;J;;2026-09-01 00:00:00.0;2026-12-31 23:59:00.0;18:00;;;;;;"
    "Biblioteca Ana María Matute;;;;;CARABANCHEL;;;;;;;/contenido/actividades/CursosTalleres;\n"
    "107;Alice Wonder;;0;0;;;2026-10-16 00:00:00.0;2026-10-16 23:59:00.0;21:00;"
    "Concierto de pop electrónico en directo.;;;;;Escenario móvil (Fuencarral-El Pardo);;;;;;;;;;;;"
    "/contenido/actividades/ProgramacionDestacadaAgendaCultura;/usuario/Niños,/usuario/PoblaciónGeneral\n"
)

# Formato JSON-LD del dataset 206974-0, con un salto de línea crudo y un
# escape inválido dentro de una cadena (pasa en el fichero real).
JSONLD_TEXT = """{"@context":{},"@graph":[
{"@id":"x/1","@type":"https://datos.madrid.es/egob/kos/actividades/CuentacuentosTiteresMarionetas",
 "id":"201","title":"Títeres \\'en\\' el parque","description":"Una
historia","free":1,"price":"","dtstart":"2026-10-17 00:00:00.0","dtend":"2026-10-31 23:59:00.0",
 "time":"12:00","excluded-days":"2026-10-24","recurrence":{"days":"SA,SU","frequency":"WEEKLY"},
 "link":"http://www.madrid.es/x","event-location":"Parque de El Retiro (Retiro)",
 "address":{"district":{"@id":"https://datos.madrid.es/egob/kos/Provincia/Madrid/Municipio/Madrid/Distrito/PuenteDeVallecas"}},
 "location":{"latitude":40.39,"longitude":-3.65},"audience":"Niños,Familias"},
{"@id":"x/2","@type":"https://datos.madrid.es/egob/kos/actividades/ProgramacionDestacadaAgendaCultura",
 "id":"202","title":"Gran concierto de jazz","free":0,"price":"10 €","dtstart":"2026-10-13 00:00:00.0",
 "dtend":"2026-10-13 23:59:00.0","time":"21:00","event-location":"Teatro (Centro)","address":{}}
]}"""


class HelpersTest(unittest.TestCase):
    def test_classify_uses_type_then_title(self):
        self.assertEqual(agenda.classify("/contenido/actividades/DanzaBaile", "x"), "escena")
        self.assertEqual(agenda.classify("/actividades/ProgramacionDestacadaAgendaCultura",
                                         "Concierto de otoño"), "musica")
        self.assertEqual(agenda.classify("", "Algo raro"), "otros")

    def test_district_from_text_and_uri(self):
        self.assertEqual(agenda.district_from("PUENTE DE VALLECAS"), "Puente de Vallecas")
        self.assertEqual(agenda.district_from("FUENCARRAL-EL PARDO"), "Fuencarral-El Pardo")
        self.assertEqual(agenda.district_from(".../Distrito/MoncloaAravaca"), "Moncloa-Aravaca")
        self.assertEqual(agenda.district_from("Getafe"), "")

    def test_weekdays_in_both_notations(self):
        self.assertEqual(agenda.parse_weekdays("MO,WE"), [1, 3])
        self.assertEqual(agenda.parse_weekdays("L,X,V"), [1, 3, 5])
        self.assertEqual(agenda.parse_weekdays("sábado, domingo"), [0, 6])
        self.assertIsNone(agenda.parse_weekdays(""))

    def test_district_in_text(self):
        self.assertEqual(agenda.district_in_text("Alertante de distrito (Fuencarral-El Pardo) - Mara"),
                         "Fuencarral-El Pardo")
        self.assertEqual(agenda.district_in_text("Alejandro y María Laura - Chamartin"), "Chamartín")
        self.assertEqual(agenda.district_in_text("Fiesta en Villa de Vallecas"), "Villa de Vallecas")
        self.assertEqual(agenda.district_in_text("Teatro en el distrito Centro"), "Centro")
        self.assertEqual(agenda.district_in_text("Noche de música latina", "Centro Cultural X"), "")

    def test_clean_audience(self):
        self.assertEqual(agenda.clean_audience("/usuario/Jovenes,/usuario/Familias"), "Jovenes, Familias")
        self.assertEqual(agenda.clean_audience("Niños,Familias"), "Niños, Familias")
        self.assertEqual(agenda.clean_audience(""), "")

    def test_dates_and_times(self):
        self.assertEqual(agenda.date_key("2026-10-14 00:00:00.0"), "2026-10-14")
        self.assertEqual(agenda.date_keys("20/10/2026;2026-10-27"), ["2026-10-20", "2026-10-27"])
        self.assertEqual(agenda.clean_time("9:30"), "09:30")
        self.assertEqual(agenda.clean_time(""), "")

    def test_decode_falls_back_to_cp1252(self):
        self.assertEqual(agenda.decode("Chamberí".encode("cp1252")), "Chamberí")
        self.assertEqual(agenda.decode("﻿Chamberí".encode("utf-8")), "Chamberí")


class CsvTest(unittest.TestCase):
    def setUp(self):
        self.events = agenda.normalize(CSV_TEXT, TODAY)
        self.by_title = {}
        for e in self.events:
            self.by_title.setdefault(e["title"], []).append(e)

    def test_past_events_are_dropped(self):
        self.assertNotIn("Ya pasó", self.by_title)
        self.assertEqual(len(self.events), 7)

    def test_fields(self):
        ev = self.by_title["Concierto de otoño"][0]
        self.assertEqual(ev["cat"], "musica")
        self.assertEqual(ev["district"], "Latina")
        self.assertTrue(ev["free"])
        self.assertEqual((ev["start"], ev["end"], ev["time"]), ("2026-10-14", "2026-10-14", "19:00"))
        self.assertEqual((ev["lat"], ev["lng"]), (40.4031, -3.7392))
        self.assertEqual(ev["desc"], "Primera línea\nSegunda línea")
        self.assertEqual(ev["link"], "https://www.madrid.es/ev/101")

    def test_recurrence_and_exclusions(self):
        ev = self.by_title["Taller de cerámica"][0]
        self.assertEqual(ev["cat"], "talleres")
        self.assertEqual(ev["days"], [1, 3])
        self.assertEqual(ev["excl"], ["2026-10-20"])
        self.assertEqual(ev["time"], "09:30")
        self.assertEqual(ev["district"], "Chamberí")
        self.assertFalse(ev["free"])
        self.assertNotIn("longHint", ev)

    def test_long_running_hint(self):
        ev = self.by_title["Exposición de carteles"][0]
        self.assertTrue(ev["longHint"])
        self.assertEqual(ev["cat"], "expos")

    def test_long_running_with_daily_opening_is_ongoing(self):
        ev = self.by_title["Fotografía de barrio"][0]
        self.assertTrue(ev["longHint"])
        self.assertEqual(ev["days"], [0, 2, 3, 4, 5, 6])

    def test_long_running_weekly_session_stays_in_its_day(self):
        ev = self.by_title["Club de ajedrez"][0]
        self.assertNotIn("longHint", ev)
        self.assertEqual(ev["days"], [4])

    def test_featured_programme_uses_description_and_venue(self):
        ev = self.by_title["Alice Wonder"][0]
        self.assertEqual(ev["cat"], "musica")
        self.assertEqual(ev["district"], "Fuencarral-El Pardo")
        self.assertEqual(ev["audience"], "Niños, Población general")
        self.assertTrue(ev["kids"])

    def test_ids_are_unique(self):
        ids = [e["id"] for e in self.events]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(e["id"] for e in self.by_title["Concierto de otoño"]), ["101", "101-1"])

    def test_sorted_by_date(self):
        starts = [e["start"] for e in self.events]
        self.assertEqual(starts, sorted(starts))


class JsonLdTest(unittest.TestCase):
    def setUp(self):
        self.events = {e["id"]: e for e in agenda.normalize(JSONLD_TEXT, TODAY)}

    def test_parses_dirty_json(self):
        self.assertEqual(set(self.events), {"201", "202"})
        self.assertEqual(self.events["201"]["desc"], "Una historia")

    def test_kids_recurrence_and_location(self):
        ev = self.events["201"]
        self.assertEqual(ev["cat"], "peques")
        self.assertTrue(ev["kids"])
        self.assertEqual(ev["days"], [0, 6])
        self.assertEqual(ev["excl"], ["2026-10-24"])
        self.assertEqual(ev["district"], "Puente de Vallecas")
        self.assertEqual((ev["lat"], ev["lng"]), (40.39, -3.65))

    def test_district_falls_back_to_venue(self):
        ev = self.events["202"]
        self.assertEqual(ev["district"], "Centro")
        self.assertEqual(ev["cat"], "musica")
        self.assertFalse(ev["free"])
        self.assertEqual(ev["price"], "10 €")


class AppContractTest(unittest.TestCase):
    """Las claves que lee site/index.html."""
    KEYS = {"id", "title", "desc", "cat", "kids", "free", "price", "start", "end", "time",
            "days", "excl", "venue", "district", "lat", "lng", "link", "audience"}
    CATS = {c for c, _ in agenda.CATEGORIES} | {"otros"}

    def test_every_event_has_the_app_keys(self):
        for text in (CSV_TEXT, JSONLD_TEXT):
            for ev in agenda.normalize(text, TODAY):
                self.assertLessEqual(self.KEYS, set(ev))
                self.assertIn(ev["cat"], self.CATS)

    def test_cli_writes_payload_from_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "agenda.csv", Path(tmp) / "out" / "agenda.json"
            src.write_bytes(CSV_TEXT.encode("cp1252"))
            self.assertEqual(fetch_agenda.main(["--input", str(src), "--out", str(out), "--min-events", "1", "--today", "2026-10-12"]), 0)
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(payload["count"], len(payload["events"]))
            self.assertIn("generatedAt", payload)

    def test_cli_keeps_old_file_when_too_few_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "agenda.csv", Path(tmp) / "agenda.json"
            src.write_text(CSV_TEXT, encoding="utf-8")
            out.write_text('{"previo":true}', encoding="utf-8")
            self.assertEqual(fetch_agenda.main(["--input", str(src), "--out", str(out), "--today", "2026-10-12"]), 1)
            self.assertEqual(out.read_text(encoding="utf-8"), '{"previo":true}')


if __name__ == "__main__":
    unittest.main()
