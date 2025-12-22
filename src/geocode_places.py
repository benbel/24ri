#!/usr/bin/env python3
"""
Geocoding script for extracted places using the French IGN API.
Supports YAML corrections file with OK/N/A/coords/name logic.
"""

import json
import time
import os
import re
import requests
import yaml

GEOCODE_URL = "https://data.geopf.fr/geocodage/search"

# France metropolitan bounding box
FRANCE_BOUNDS = {
    'min_lat': 41.0,
    'max_lat': 51.5,
    'min_lon': -5.5,
    'max_lon': 10.0,
}


def load_corrections(corrections_path: str) -> dict:
    """
    Load corrections from YAML file.
    Format: {id: {original: "...", correction: "OK|N/A|(lat,lon)|name"}}
    """
    if not os.path.exists(corrections_path):
        return {}

    with open(corrections_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    corrections = {}
    for entity_id, entry in data.items():
        correction = entry.get('correction', 'OK')
        corrections[entity_id] = correction

    return corrections


def parse_correction(correction: str) -> tuple[str, any]:
    """
    Parse a correction value.
    Returns (type, value) where type is one of: 'ok', 'na', 'coords', 'name'
    """
    if correction is None or correction == 'OK':
        return ('ok', None)

    if correction == 'N/A':
        return ('na', None)

    # Check for coordinates: (lat, lon) or lat,lon
    coord_match = re.match(r'\(?\s*(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)\s*\)?', correction)
    if coord_match:
        lat = float(coord_match.group(1))
        lon = float(coord_match.group(2))
        return ('coords', (lat, lon))

    # Otherwise, it's a replacement name to geocode
    return ('name', correction)


def is_in_france(lat: float, lon: float) -> bool:
    """Check if coordinates are in metropolitan France."""
    return (FRANCE_BOUNDS['min_lat'] <= lat <= FRANCE_BOUNDS['max_lat'] and
            FRANCE_BOUNDS['min_lon'] <= lon <= FRANCE_BOUNDS['max_lon'])


def geocode_place(place_name: str, retry_count: int = 3) -> dict | None:
    """Geocode a place name using the IGN API."""
    place_clean = place_name.replace('\n', ' ').strip()

    if len(place_clean) < 2:
        return None

    for attempt in range(retry_count):
        try:
            params = {
                'q': place_clean,
                'limit': 5,
                'autocomplete': 0,
            }

            response = requests.get(GEOCODE_URL, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if data.get('features'):
                for feature in data['features']:
                    coords = feature['geometry']['coordinates']
                    lat, lon = coords[1], coords[0]

                    if is_in_france(lat, lon):
                        props = feature['properties']
                        return {
                            'matched_name': props.get('name', props.get('label', '')),
                            'latitude': lat,
                            'longitude': lon,
                            'type': props.get('type', ''),
                            'city': props.get('city', ''),
                            'context': props.get('context', ''),
                            'score': props.get('score', 0),
                        }

            return None

        except requests.RequestException as e:
            if attempt < retry_count - 1:
                time.sleep(1)
            else:
                print(f"  Error geocoding '{place_name}': {e}")
                return None

    return None


def geocode_chapters(input_path: str, output_path: str, corrections_path: str):
    """
    Geocode all places from chapters file.
    Applies corrections: OK=geocode, N/A=skip, (lat,lon)=use coords, name=geocode replacement
    """
    print(f"Reading chapters from: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chapters = data.get('chapters', [])
    all_places = data.get('all_places', [])
    all_dates = data.get('all_dates', [])

    corrections = load_corrections(corrections_path)
    print(f"Loaded {len(corrections)} corrections")

    # Cache for geocoded names (avoid duplicate API calls)
    geocode_cache = {}

    # Process each place with its correction
    geocoded_places = []
    not_found = []
    excluded = []

    for i, place in enumerate(all_places):
        entity_id = place['id']
        original_name = place['text']

        print(f"  [{i+1}/{len(all_places)}] {original_name[:40]}...", end=' ')

        # Get correction type
        correction = corrections.get(entity_id, 'OK')
        ctype, cvalue = parse_correction(correction)

        if ctype == 'na':
            excluded.append(place)
            print("EXCLUDED (N/A)")
            continue

        if ctype == 'coords':
            # Direct coordinates provided
            lat, lon = cvalue
            place['geocoded'] = {
                'display_name': original_name,
                'matched_name': original_name,
                'latitude': lat,
                'longitude': lon,
                'type': 'manual',
                'source': 'correction',
            }
            geocoded_places.append(place)
            print(f"-> COORDS ({lat:.4f}, {lon:.4f})")
            continue

        # Geocode (either original name or replacement)
        name_to_geocode = cvalue if ctype == 'name' else original_name

        # Check cache first
        if name_to_geocode in geocode_cache:
            result = geocode_cache[name_to_geocode]
            print("(cached)", end=' ')
        else:
            result = geocode_place(name_to_geocode)
            geocode_cache[name_to_geocode] = result
            time.sleep(0.1)

        if result:
            place['geocoded'] = {
                'display_name': original_name,
                'matched_name': result['matched_name'],
                'latitude': result['latitude'],
                'longitude': result['longitude'],
                'type': result['type'],
                'source': 'geocoded' if ctype == 'ok' else 'corrected_name',
            }
            geocoded_places.append(place)
            geocoded_name = name_to_geocode if ctype == 'name' else result['matched_name']
            print(f"-> {geocoded_name[:30]} ({result['latitude']:.3f}, {result['longitude']:.3f})")
        else:
            not_found.append(place)
            print("NOT FOUND")

    print(f"\nResults: {len(geocoded_places)} found, {len(not_found)} not found, {len(excluded)} excluded")

    # Update chapters with geocoded info
    place_geocoded_map = {p['id']: p.get('geocoded') for p in geocoded_places}

    for chapter in chapters:
        for place in chapter.get('places', []):
            if place['id'] in place_geocoded_map:
                place['geocoded'] = place_geocoded_map[place['id']]

        for segment in chapter.get('segments', []):
            segment['geocoded_places'] = []
            for place in segment.get('places', []):
                if place['id'] in place_geocoded_map:
                    place['geocoded'] = place_geocoded_map[place['id']]
                    segment['geocoded_places'].append(place['geocoded'])

    # Save results
    output_data = {
        'chapters': chapters,
        'all_places': all_places,
        'all_dates': all_dates,
        'geocoded_places': geocoded_places,
        'not_found': [p['text'] for p in not_found],
        'excluded': [p['text'] for p in excluded],
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"Saved to: {output_path}")
    return output_data


if __name__ == "__main__":
    input_path = "output/chapters.json"
    output_path = "output/chapters_geocoded.json"
    corrections_path = "output/corrections/places_corrections.yaml"

    geocode_chapters(input_path, output_path, corrections_path)
