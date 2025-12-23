#!/usr/bin/env python3
"""
Generate static index.html from chunks.json.
"""

import csv
import json
import os
import re
from jinja2 import Environment, FileSystemLoader


def load_chunks(chunks_path: str) -> list:
    """Load chunks from JSON file."""
    with open(chunks_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_places(places_path: str) -> list:
    """Load all places with coordinates from CSV."""
    places = []
    with open(places_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            places.append({
                'name': row['name'],
                'latitude': float(row['latitude']),
                'longitude': float(row['longitude']),
            })
    return places


def prepare_chunks_for_template(chunks: list) -> list:
    """
    Prepare chunks for the template.
    Converts the intermediate format to the template format.
    """
    template_chunks = []

    for chunk in chunks:
        # Build places list with geocoded info
        places = []
        for place in chunk.get('places', []):
            places.append({
                'text': place['name'],
                'display_name': place['name'],
                'geocoded': {
                    'latitude': place['latitude'],
                    'longitude': place['longitude'],
                }
            })

        # Format date for header
        date_display = ""
        if chunk.get('date_start') and chunk.get('date_end'):
            if chunk['date_start'] == chunk['date_end']:
                date_display = chunk['date_start']
            else:
                date_display = f"{chunk['date_start']} - {chunk['date_end']}"
        elif chunk.get('date_start'):
            date_display = chunk['date_start']

        template_chunks.append({
            'chapter_number': chunk['chapter'],
            'chapter_title': chunk['chapter_title'],
            'text': chunk['text'],
            'date': date_display,
            'dates': chunk.get('dates', []),
            'places': places,
        })

    return template_chunks


def generate_index(chunks: list, all_places: list, template_dir: str, output_path: str):
    """Generate the main index.html page."""
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('index.html')

    template_chunks = prepare_chunks_for_template(chunks)
    chunks_json = json.dumps(template_chunks, ensure_ascii=False)
    all_places_json = json.dumps(all_places, ensure_ascii=False)

    html = template.render(chunks_json=chunks_json, all_places_json=all_places_json)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated: {output_path} ({len(template_chunks)} chunks, {len(all_places)} places)")


def main():
    # Input/output paths
    chunks_manual = "manual_modifications/chunks.json"
    chunks_default = "output/chunks.json"
    places_path = "output/places_final.csv"
    template_dir = "templates"
    output_path = "output/webapp/index.html"

    # Find chunks file
    if os.path.exists(chunks_manual):
        chunks_path = chunks_manual
        print(f"Using: {chunks_manual}")
    elif os.path.exists(chunks_default):
        chunks_path = chunks_default
        print(f"Using: {chunks_default}")
    else:
        print("Error: No chunks.json found")
        return

    # Load places
    if not os.path.exists(places_path):
        print(f"Error: {places_path} not found")
        return

    chunks = load_chunks(chunks_path)
    print(f"Loaded {len(chunks)} chunks")

    all_places = load_all_places(places_path)
    print(f"Loaded {len(all_places)} places")

    generate_index(chunks, all_places, template_dir, output_path)
    print("\nDone!")


if __name__ == "__main__":
    main()
