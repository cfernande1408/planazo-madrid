# Planazo Madrid

Qué pasa en Madrid, día a día. Una web app (Material Design 3) con:

- **Para ti**: hoy, mañana, este finde, tus barrios y la semana, ordenado por tus intereses.
- **Calendario**: mes con puntos de color por tipo de plan y agenda del día por franjas.
- **Intereses**: tipos de plan, distritos favoritos, franjas horarias, solo gratis y planes con peques.

Fuentes de datos (un GitHub Action las lee cada mañana y vuelve a publicar la web):

- **Ayuntamiento de Madrid**: agenda del
  [portal de datos abiertos](https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos)
  (CC BY 4.0). Obligatoria: si no se puede descargar, se publica la última versión.
- **Comunidad de Madrid**: [RSS de actividades](https://www.comunidad.madrid/rss/latest-events.xml)
  y la ficha de cada una. El RSS solo trae las 20 últimas, así que se acumulan
  en `data/comunidad.json`. Las de otros municipios se muestran si activas
  «Planes en otros municipios».

## Estructura

```
site/                  la web que se publica en GitHub Pages
  index.html           app completa (HTML + CSS + JS, sin dependencias)
  data/agenda.json     agenda normalizada (la genera el workflow)
scripts/
  agenda.py            normalización: CSV actual y JSON-LD antiguo → formato de la app
  comunidad.py         RSS + fichas de comunidad.madrid → formato de la app
  fetch_agenda.py      descarga, fusión de fuentes y escritura de site/data/agenda.json
data/comunidad.json    caché acumulativa de la Comunidad (la mantiene el workflow)
tests/                 tests (unittest, sin dependencias)
.github/workflows/pages.yml   tests → descarga diaria → commit de datos → deploy
```

Las preferencias y los guardados viven en el `localStorage` de cada navegador.

## Publicar en GitHub Pages

Con [GitHub CLI](https://cli.github.com/) y sesión iniciada (`gh auth login`):

```bash
gh repo create planazo-madrid --public --source=. --remote=origin
gh api -X POST "repos/{owner}/{repo}/pages" -f build_type=workflow
git push -u origin main
gh run watch
```

La web queda en `https://<tu-usuario>.github.io/planazo-madrid/`.

Para forzar una actualización de datos sin esperar a mañana:

```bash
gh workflow run pages.yml && gh run watch
```

## Desarrollo local

```bash
python -m unittest discover -s tests -v   # tests
python scripts/fetch_agenda.py            # descarga la agenda real a site/data/
python -m http.server -d site 8000        # http://localhost:8000
```

Sin `site/data/agenda.json` la app muestra datos de ejemplo, marcados como tales.

Para comprobar el parser de la Comunidad contra la web real sin escribir nada:

```bash
python scripts/comunidad.py --limit 5
```

Si el Action no consigue descargar la agenda (el portal a veces falla o cambia
de URL), el workflow publica la última versión guardada. También puedes bajar
el CSV a mano y normalizarlo:

```bash
python scripts/fetch_agenda.py --input ~/Descargas/agenda.csv
git add site/data/agenda.json && git commit -m "chore(data): actualizar agenda" && git push
```

## Ideas pendientes

- Más fuentes: agenda de la Comunidad de Madrid y salas privadas.
- Instalable como PWA (manifest + iconos).
