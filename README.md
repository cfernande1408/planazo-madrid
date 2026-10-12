# Planazo Madrid

Qué pasa en Madrid, día a día. Una web app (Material Design 3) con:

- **Para ti**: hoy, mañana, este finde, tus barrios y la semana, ordenado por tus intereses.
- **Calendario**: mes con puntos de color por tipo de plan y agenda del día por franjas.
- **Intereses**: tipos de plan, distritos favoritos, franjas horarias, solo gratis y planes con peques.

Los datos salen de la agenda de actividades del
[portal de datos abiertos del Ayuntamiento de Madrid](https://datos.madrid.es/dataset/300107-0-agenda-actividades-eventos)
(licencia CC BY 4.0). Un GitHub Action la descarga cada mañana y vuelve a publicar la web.

## Estructura

```
site/                  la web que se publica en GitHub Pages
  index.html           app completa (HTML + CSS + JS, sin dependencias)
  data/agenda.json     agenda normalizada (la genera el workflow)
scripts/
  agenda.py            normalización: CSV actual y JSON-LD antiguo → formato de la app
  fetch_agenda.py      descarga + escritura de site/data/agenda.json
tests/test_agenda.py   tests del normalizador (unittest, sin dependencias)
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
