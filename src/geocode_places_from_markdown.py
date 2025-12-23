#!/usr/bin/env python3
"""
Geocode places extracted from NER markdown using batch CSV API.
Reads [[place]] patterns, gets unique values, geocodes them in batch, saves to CSV.
"""

import csv
import io
import os
import re
import requests

GEOCODE_BATCH_URL = "https://data.geopf.fr/geocodage/search/csv"


def extract_places_from_markdown(filepath: str) -> list[str]:
    """Extract all [[place]] patterns from markdown file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find all [[...]] patterns
    places = re.findall(r'\[\[([^\]]+)\]\]', content)
    return places


def get_unique_places(places: list[str]) -> list[str]:
    """Get unique place names, preserving first occurrence order."""
    seen = set()
    unique = []
    for place in places:
        place_normalized = place.strip()
        if place_normalized and place_normalized.lower() not in seen:
            seen.add(place_normalized.lower())
            unique.append(place_normalized)
    return unique


def create_csv_for_batch(places: list[str]) -> str:
    """Create CSV content for batch geocoding."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'name'])
    for i, place in enumerate(places):
        writer.writerow([i, place])
    return output.getvalue()


def batch_geocode(places: list[str]) -> list[dict]:
    """
    Geocode places using the batch CSV API.
    Returns list of results with original name, matched name, and coordinates.
    """
    print(f"Preparing batch request for {len(places)} places...")

    # Create CSV content
    csv_content = create_csv_for_batch(places)

    # Send batch request
    files = {
        'data': ('places.csv', csv_content, 'text/csv')
    }
    params = {
        'columns': 'name',
        'result_columns': 'result_label,result_score,result_type,latitude,longitude',
    }

    print("Sending batch geocoding request...")
    response = requests.post(GEOCODE_BATCH_URL, files=files, params=params, timeout=120)
    response.raise_for_status()

    # Parse response CSV
    results = []
    reader = csv.DictReader(io.StringIO(response.text))

    # Accepted types for automatic validation
    accepted_types = {'municipality', 'locality'}

    for row in reader:
        lat = row.get('latitude', '')
        lon = row.get('longitude', '')
        result_type = row.get('result_type', '')

        # Determine status based on coordinates and type
        if lat and lon:
            try:
                float(lat)
                float(lon)
                if result_type in accepted_types:
                    status = 'found'
                else:
                    status = 'review'  # Found but wrong type, needs manual review
            except ValueError:
                status = 'not_found'
                lat = ''
                lon = ''
        else:
            status = 'not_found'

        results.append({
            'original_name': row.get('name', ''),
            'matched_name': row.get('result_label', ''),
            'latitude': lat,
            'longitude': lon,
            'type': result_type,
            'score': row.get('result_score', ''),
            'status': status,
        })

    return results


def save_to_csv(results: list[dict], output_path: str):
    """Save geocoding results to CSV."""
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    fieldnames = ['original_name', 'matched_name', 'latitude', 'longitude', 'type', 'score', 'status']

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved to: {output_path}")


def main():
    # Check for manual modifications first
    manual_path = "manual_modifications/ner_document.md"
    default_path = "output/ner_document.md"
    output_path = "output/places_geocoded.csv"

    if os.path.exists(manual_path):
        input_path = manual_path
        print(f"Using manually corrected file: {manual_path}")
    elif os.path.exists(default_path):
        input_path = default_path
        print(f"Using generated file: {default_path}")
    else:
        print(f"Error: No input file found.")
        print(f"  Expected: {manual_path} or {default_path}")
        return

    # Extract places
    print(f"\nExtracting places from: {input_path}")
    all_places = extract_places_from_markdown(input_path)
    print(f"Found {len(all_places)} place mentions")

    # Get unique places
    unique_places = get_unique_places(all_places)
    print(f"Unique places: {len(unique_places)}")

    # Batch geocode
    print(f"\nGeocoding {len(unique_places)} places (batch mode)...")
    results = batch_geocode(unique_places)

    # Stats
    found = sum(1 for r in results if r['status'] == 'found')
    review = sum(1 for r in results if r['status'] == 'review')
    not_found = sum(1 for r in results if r['status'] == 'not_found')
    print(f"\nResults: {found} found (municipality/locality), {review} to review, {not_found} not found")

    # Save
    save_to_csv(results, output_path)


if __name__ == "__main__":
    main()
