#!/usr/bin/env python3
"""
Generate chunks JSON from NER markdown.
Chunks are split by chapters, French quotes context, and max 10 sentences.
Includes coordinates and date ranges.
"""

import csv
import json
import os
import re
from datetime import datetime

# French months mapping
MONTHS_FR = {
    'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
    'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
    'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
}


def load_places(filepath: str) -> dict:
    """Load places with coordinates from CSV."""
    places = {}
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row['name'].lower()
            places[name] = {
                'name': row['name'],
                'latitude': float(row['latitude']),
                'longitude': float(row['longitude']),
            }
    return places


def load_markdown(filepath: str) -> str:
    """Load markdown content."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def parse_date(date_str: str, current_year: int = None) -> tuple:
    """
    Parse a French date string and return (year, month).
    Handles: "17 mai 1917", "mai 1917", "17 mai"
    """
    date_str = date_str.lower().strip()

    # Pattern: day month year (e.g., "17 mai 1917")
    match = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{4})', date_str)
    if match:
        month_name = match.group(2)
        year = int(match.group(3))
        month = MONTHS_FR.get(month_name, 1)
        return (year, month)

    # Pattern: month year (e.g., "mai 1917")
    match = re.match(r'(\w+)\s+(\d{4})', date_str)
    if match:
        month_name = match.group(1)
        year = int(match.group(2))
        month = MONTHS_FR.get(month_name, 1)
        return (year, month)

    # Pattern: day month (e.g., "17 mai") - use current year
    match = re.match(r'(\d{1,2})\s+(\w+)', date_str)
    if match:
        month_name = match.group(2)
        month = MONTHS_FR.get(month_name)
        if month and current_year:
            return (current_year, month)

    return None


def extract_chapter_content(markdown: str) -> list:
    """
    Extract chapters from markdown.
    Returns list of {title, number, lines}
    """
    chapters = []
    current_chapter = None
    current_lines = []

    for line in markdown.split('\n'):
        # Check for chapter heading (## ...)
        match = re.match(r'^##\s+(.+)$', line.strip())
        if match:
            # Save previous chapter
            if current_chapter:
                current_chapter['lines'] = current_lines
                chapters.append(current_chapter)

            title = match.group(1)
            # Extract roman numeral if present
            num_match = re.match(r'^([IVXLCDM]+)\.\s*(.+)$', title)
            if num_match:
                current_chapter = {
                    'number': num_match.group(1),
                    'title': num_match.group(2).strip(),
                }
            else:
                current_chapter = {
                    'number': None,
                    'title': title,
                }
            current_lines = []
        elif current_chapter:
            if line.strip():
                current_lines.append(line.strip())

    # Save last chapter
    if current_chapter:
        current_chapter['lines'] = current_lines
        chapters.append(current_chapter)

    return chapters


def has_french_quote(text: str) -> bool:
    """Check if text contains French quotes « »."""
    return '«' in text or '»' in text


def is_quote_start(text: str) -> bool:
    """Check if text starts a French quote."""
    return '«' in text and '»' not in text


def is_quote_end(text: str) -> bool:
    """Check if text ends a French quote."""
    return '»' in text and '«' not in text


def is_inside_quote(text: str) -> bool:
    """Check if text is inside quotes (has » but no «, or has both)."""
    return '«' in text or '»' in text


def extract_entities(text: str) -> tuple:
    """Extract [[places]] and {{dates}} from text."""
    places = re.findall(r'\[\[([^\]]+)\]\]', text)
    dates = re.findall(r'\{\{([^}]+)\}\}', text)
    return places, dates


def count_places_in_lines(lines: list) -> int:
    """Count unique places in a list of lines."""
    text = '\n'.join(lines)
    places = re.findall(r'\[\[([^\]]+)\]\]', text)
    return len(set(places))


def create_chunks(chapter: dict, max_sentences: int = 10, max_places: int = 5) -> list:
    """
    Create chunks from chapter lines following the rules:
    - French quotes and preceding sentence stay together
    - Max 10 sentences per chunk
    - Max 5 unique places per chunk
    """
    chunks = []
    current_chunk_lines = []
    in_quote = False

    for i, line in enumerate(chapter['lines']):
        # Check quote status
        if '«' in line:
            in_quote = True

        current_chunk_lines.append(line)

        if '»' in line:
            in_quote = False

        # Determine if we should start a new chunk
        should_split = False

        if not in_quote:
            # Check if next line starts a quote - if so, don't split here
            next_starts_quote = False
            if i + 1 < len(chapter['lines']):
                next_starts_quote = '«' in chapter['lines'][i + 1]

            if not next_starts_quote:
                # Split if max sentences reached OR max places exceeded
                if len(current_chunk_lines) >= max_sentences:
                    should_split = True
                elif count_places_in_lines(current_chunk_lines) > max_places:
                    should_split = True

        if should_split:
            chunks.append({
                'lines': current_chunk_lines,
                'text': '\n'.join(current_chunk_lines),
            })
            current_chunk_lines = []

    # Add remaining lines
    if current_chunk_lines:
        chunks.append({
            'lines': current_chunk_lines,
            'text': '\n'.join(current_chunk_lines),
        })

    return chunks


def determine_date_range(dates: list, prev_end: tuple, current_year: int) -> tuple:
    """
    Determine start and end date for a chunk based on extracted dates.
    Returns ((start_year, start_month), (end_year, end_month), updated_current_year)
    """
    if not dates:
        return (prev_end, prev_end, current_year)

    parsed_dates = []
    for date_str in dates:
        parsed = parse_date(date_str, current_year)
        if parsed:
            parsed_dates.append(parsed)
            # Update current year if we found a full year
            if parsed[0]:
                current_year = parsed[0]

    if not parsed_dates:
        return (prev_end, prev_end, current_year)

    # Sort dates
    parsed_dates.sort()

    start_date = parsed_dates[0]
    end_date = parsed_dates[-1]

    # Ensure we don't go backwards
    if prev_end and start_date < prev_end:
        start_date = prev_end

    if end_date < start_date:
        end_date = start_date

    return (start_date, end_date, current_year)


def format_date(date_tuple: tuple) -> str:
    """Format (year, month) as 'MM/YYYY'."""
    if not date_tuple:
        return None
    year, month = date_tuple
    return f"{month:02d}/{year}"


def process_chunks(chapters: list, places_coords: dict) -> list:
    """
    Process all chapters into chunks with metadata.
    """
    all_chunks = []
    chunk_id = 0
    prev_end_date = (1914, 8)  # Start of WWI
    current_year = 1914

    for chapter in chapters:
        chapter_chunks = create_chunks(chapter)

        for chunk in chapter_chunks:
            # Extract entities
            places, dates = extract_entities(chunk['text'])

            # Get coordinates for places
            chunk_places = []
            for place in places:
                place_lower = place.lower()
                if place_lower in places_coords:
                    chunk_places.append({
                        'name': place,
                        **places_coords[place_lower]
                    })

            # Determine date range
            start_date, end_date, current_year = determine_date_range(
                dates, prev_end_date, current_year
            )

            # Create chunk object
            chunk_obj = {
                'id': chunk_id,
                'chapter': chapter['number'] or chapter['title'],
                'chapter_title': chapter['title'],
                'text': chunk['text'],
                'sentence_count': len(chunk['lines']),
                'places': chunk_places,
                'dates': dates,
                'date_start': format_date(start_date),
                'date_end': format_date(end_date),
            }

            all_chunks.append(chunk_obj)
            prev_end_date = end_date
            chunk_id += 1

    return all_chunks


def validate_chronology(chunks: list) -> list:
    """
    Validate and fix chronological order of chunks.
    Returns list of warnings.
    """
    warnings = []

    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        curr = chunks[i]

        if prev['date_end'] and curr['date_start']:
            # Parse dates for comparison
            prev_end = prev['date_end'].split('/')
            curr_start = curr['date_start'].split('/')

            prev_end_tuple = (int(prev_end[1]), int(prev_end[0]))
            curr_start_tuple = (int(curr_start[1]), int(curr_start[0]))

            if curr_start_tuple < prev_end_tuple:
                warnings.append(
                    f"Chunk {curr['id']}: starts {curr['date_start']} before "
                    f"chunk {prev['id']} ends {prev['date_end']}"
                )
                # Fix by adjusting start date
                curr['date_start'] = prev['date_end']

    return warnings


def main():
    # Input files
    md_manual = "manual_modifications/ner_document.md"
    md_default = "output/ner_document.md"
    places_path = "output/places_final.csv"
    output_path = "output/chunks.json"

    # Find markdown file
    if os.path.exists(md_manual):
        md_path = md_manual
        print(f"Using markdown: {md_manual}")
    elif os.path.exists(md_default):
        md_path = md_default
        print(f"Using markdown: {md_default}")
    else:
        print("Error: No ner_document.md found")
        return

    # Load data
    if not os.path.exists(places_path):
        print(f"Error: {places_path} not found")
        return

    places_coords = load_places(places_path)
    print(f"Loaded {len(places_coords)} places with coordinates")

    markdown = load_markdown(md_path)
    chapters = extract_chapter_content(markdown)
    print(f"Found {len(chapters)} chapters")

    # Process into chunks
    chunks = process_chunks(chapters, places_coords)
    print(f"Created {len(chunks)} chunks")

    # Validate chronology
    warnings = validate_chronology(chunks)
    if warnings:
        print(f"\nChronology warnings ({len(warnings)}):")
        for w in warnings[:10]:
            print(f"  - {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")

    # Stats
    total_places = sum(len(c['places']) for c in chunks)
    total_dates = sum(len(c['dates']) for c in chunks)
    print(f"\nTotal place mentions with coords: {total_places}")
    print(f"Total date mentions: {total_dates}")

    # Save
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
