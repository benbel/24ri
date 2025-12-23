#!/usr/bin/env python3
"""
Generate final places CSV from corrected data.
Filters out excluded places and keeps only valid coordinates.
"""

import csv
import os


def load_corrected_csv(filepath: str) -> list[dict]:
    """Load corrected places from CSV."""
    places = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            places.append(row)
    return places


def is_valid_coords(lat: str, lon: str) -> bool:
    """Check if coordinates are valid numbers."""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
        return -90 <= lat_f <= 90 and -180 <= lon_f <= 180
    except (ValueError, TypeError):
        return False


def process_places(places: list[dict]) -> list[dict]:
    """
    Process places and return only valid ones.
    Filters out excluded places and those without valid coordinates.
    """
    valid_places = []
    excluded_count = 0
    no_coords_count = 0

    for place in places:
        status = place.get('status', '')
        lat = place.get('latitude', '')
        lon = place.get('longitude', '')

        # Skip excluded places
        if status == 'excluded':
            excluded_count += 1
            continue

        # Skip places without valid coordinates
        if not is_valid_coords(lat, lon):
            no_coords_count += 1
            continue

        valid_places.append({
            'name': place.get('original_name', ''),
            'latitude': float(lat),
            'longitude': float(lon),
            'status': status,
        })

    print(f"Excluded: {excluded_count}")
    print(f"No valid coordinates: {no_coords_count}")
    print(f"Valid places: {len(valid_places)}")

    return valid_places


def save_final_csv(places: list[dict], output_path: str):
    """Save final places to CSV."""
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    fieldnames = ['name', 'latitude', 'longitude', 'status']

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(places)

    print(f"Saved to: {output_path}")


def main():
    # Input files
    manual_path = "manual_modifications/places_corrected.csv"
    default_path = "output/places_corrected.csv"
    output_path = "output/places_final.csv"

    # Find input file
    if os.path.exists(manual_path):
        input_path = manual_path
        print(f"Using: {manual_path}")
    elif os.path.exists(default_path):
        input_path = default_path
        print(f"Using: {default_path}")
    else:
        print("Error: No places_corrected.csv found")
        return

    # Load and process
    places = load_corrected_csv(input_path)
    print(f"Loaded {len(places)} places")

    valid_places = process_places(places)

    # Save
    save_final_csv(valid_places, output_path)


if __name__ == "__main__":
    main()
