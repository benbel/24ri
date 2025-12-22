# 24ri

Historique du 24e Régiment d'Infanterie (1914-1918) - Visualisation interactive sur carte.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Commandes

### Geocodage des lieux

Applique les corrections depuis `output/corrections/places_corrections.yaml` et géocode les lieux:

```bash
source .venv/bin/activate
python src/geocode_places.py
```

### Génération des pages web

Génère `index.html` et `debug.html` dans `output/webapp/`:

```bash
source .venv/bin/activate
python src/generate_webpage.py
```

## Notes

- pour les dates, elles sont uniques par phrase i.e. 30 peut correspondre à une
  date dans une phrase, mais pas dans une autre. Idem selon la phrase, le 25
août peut faire référence à plusieurs années différentes.
