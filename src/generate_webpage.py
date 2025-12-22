#!/usr/bin/env python3
"""
Generate static webpages using Jinja2 templates.
Creates index.html (historical map view) and debug.html (correction interface).
"""

import json
import os
import re
from jinja2 import Environment, FileSystemLoader


def load_data(data_path: str) -> dict:
    """Load geocoded chapters data."""
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_month_year(date_text: str, default_year: str = None) -> str:
    """Extract month + year from a date string."""
    months = [
        'janvier', 'février', 'mars', 'avril', 'mai', 'juin',
        'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
    ]

    # Find month
    month = None
    for m in months:
        if m in date_text.lower():
            month = m
            break

    if not month:
        return date_text

    # Find year (191X pattern)
    year_match = re.search(r'19\d{2}', date_text)
    year = year_match.group() if year_match else default_year

    if year:
        return f"{month} {year}"
    else:
        return month


def find_chapter_year(chapter_dates: list) -> str:
    """Find the most common year in chapter dates."""
    for date in chapter_dates:
        year_match = re.search(r'19\d{2}', date.get('text', ''))
        if year_match:
            return year_match.group()
    return None


def clean_text(text: str) -> str:
    """Remove unwanted elements from text."""
    # Remove "ANNÉE 191X" and "ANNÉE 1914-1918" style headers
    text = re.sub(r'\s*ANNÉE\s+191\d(?:-191\d)?\s*', ' ', text)
    # Clean up multiple spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, handling French abbreviations."""
    # Common French abbreviations that end with a period
    abbreviations = {
        'R.I.', 'C.A.', 'D.I.', 'B.I.', 'A.D.', 'A.C.', 'P.C.', 'Q.G.',
        'M.', 'MM.', 'Mme.', 'Mlle.', 'Dr.', 'St.', 'Ste.',
        'etc.', 'cf.', 'ex.', 'vol.', 'p.', 'pp.', 'n°.',
        'av.', 'apr.', 'J.-C.', 'Cie.', 'Cie.',
    }

    # Replace abbreviations with placeholders to protect them
    protected = text
    placeholder_map = {}
    for i, abbr in enumerate(abbreviations):
        placeholder = f"__ABBR{i}__"
        placeholder_map[placeholder] = abbr
        protected = protected.replace(abbr, placeholder)

    # Also protect patterns like "1e.", "2e.", "24e.", "IIe.", etc.
    protected = re.sub(r'(\d+e)\.', r'\1__DOT__', protected)
    protected = re.sub(r'([IVX]+e)\.', r'\1__DOT__', protected)

    # Split on sentence-ending punctuation followed by space and uppercase, or end
    sentences = []
    # Split on . ! ? followed by space(s) and uppercase letter, or end of string
    parts = re.split(r'([.!?]+)(?:\s+)(?=[A-ZÀ-ÖØ-Þ]|$)', protected)

    # Reconstruct sentences
    current = ""
    for i, part in enumerate(parts):
        current += part
        # If this part is punctuation and next would start a new sentence
        if re.match(r'^[.!?]+$', part) and i < len(parts) - 1:
            if current.strip():
                sentences.append(current.strip())
            current = ""

    if current.strip():
        sentences.append(current.strip())

    # Restore abbreviations and protected dots
    restored = []
    for sent in sentences:
        for placeholder, abbr in placeholder_map.items():
            sent = sent.replace(placeholder, abbr)
        sent = sent.replace('__DOT__', '.')
        restored.append(sent)

    return restored


def find_sentence_index(sentences: list[str], place_sentence: str) -> int:
    """Find which sentence index contains this place's sentence."""
    # Try exact match first
    for i, s in enumerate(sentences):
        if place_sentence.strip() in s or s in place_sentence.strip():
            return i
    # Fallback: find by overlap
    place_words = set(place_sentence.split())
    best_idx = 0
    best_overlap = 0
    for i, s in enumerate(sentences):
        sent_words = set(s.split())
        overlap = len(place_words & sent_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_idx = i
    return best_idx


def build_chunks(data: dict) -> list[dict]:
    """
    Build navigation chunks from chapters data.

    A chunk = text from one NER'd place to the next (or end of chapter).
    Merge chunks if places are < 5 sentences apart (unless merged > 10 sentences).
    """
    chunks = []
    current_year = None  # Track year across chapters

    for chapter in data.get('chapters', []):
        chapter_num = chapter['number']
        chapter_title = chapter['title']
        chapter_text = clean_text(chapter.get('text', ''))

        # Split chapter into sentences
        sentences = split_into_sentences(chapter_text)
        if not sentences:
            continue

        # Get geocoded places and find their sentence indices
        geocoded_places = []
        for place in chapter.get('places', []):
            if place.get('geocoded'):
                sent_idx = find_sentence_index(sentences, place.get('sentence', ''))
                geocoded_places.append({
                    'id': place['id'],
                    'text': place['text'],
                    'display_name': place['geocoded'].get('display_name', place['text']),
                    'geocoded': place['geocoded'],
                    'sentence_idx': sent_idx,
                })

        if not geocoded_places:
            # No geocoded places in this chapter, skip
            continue

        # Sort places by sentence index
        geocoded_places.sort(key=lambda p: p['sentence_idx'])

        # Build initial chunks (from previous place to current place, including intro text)
        raw_chunks = []
        for i, place in enumerate(geocoded_places):
            # Start from beginning (for first place) or from previous place's sentence
            if i == 0:
                start_idx = 0  # Include text before first place
            else:
                start_idx = geocoded_places[i - 1]['sentence_idx'] + 1

            end_idx = place['sentence_idx'] + 1  # Include the place's sentence

            # Skip if empty range (places in same sentence)
            if start_idx >= end_idx:
                # Merge with previous chunk if exists
                if raw_chunks:
                    raw_chunks[-1]['places'].append(place)
                    raw_chunks[-1]['end_idx'] = end_idx
                continue

            raw_chunks.append({
                'start_idx': start_idx,
                'end_idx': end_idx,
                'places': [place],
            })

        # Add remaining text after last place
        if geocoded_places and geocoded_places[-1]['sentence_idx'] + 1 < len(sentences):
            last_place_idx = geocoded_places[-1]['sentence_idx'] + 1
            if raw_chunks:
                # Extend last chunk to include trailing text
                raw_chunks[-1]['end_idx'] = len(sentences)

        # Merge chunks where places are < 5 sentences apart (unless > 10 total)
        merged_chunks = []
        current_chunk = None

        for chunk in raw_chunks:
            if current_chunk is None:
                current_chunk = chunk.copy()
                current_chunk['places'] = list(chunk['places'])
            else:
                # Check distance between last place in current and first in new
                last_place_idx = current_chunk['places'][-1]['sentence_idx']
                new_place_idx = chunk['places'][0]['sentence_idx']
                distance = new_place_idx - last_place_idx

                # Calculate merged size
                merged_size = chunk['end_idx'] - current_chunk['start_idx']

                if distance < 5 and merged_size <= 10:
                    # Merge: extend current chunk
                    current_chunk['end_idx'] = chunk['end_idx']
                    current_chunk['places'].extend(chunk['places'])
                else:
                    # Don't merge: save current and start new
                    merged_chunks.append(current_chunk)
                    current_chunk = chunk.copy()
                    current_chunk['places'] = list(chunk['places'])

        if current_chunk:
            merged_chunks.append(current_chunk)

        # Get dates for this chapter
        chapter_dates = chapter.get('dates', [])
        chapter_year = find_chapter_year(chapter_dates)
        if chapter_year:
            current_year = chapter_year  # Update tracked year

        # Convert to final chunk format
        for chunk in merged_chunks:
            chunk_sentences = sentences[chunk['start_idx']:chunk['end_idx']]
            chunk_text = ' '.join(chunk_sentences)

            # Find dates that appear in this chunk's text
            chunk_date = ''
            chunk_dates_list = []
            for date in chapter_dates:
                if date['text'] in chunk_text:
                    chunk_dates_list.append(date['text'])
                    # Prefer longer date formats for header (e.g., "6 août 1914" over "6 août")
                    if len(date['text']) > len(chunk_date):
                        chunk_date = date['text']
                    # Update current year if this date has one
                    year_match = re.search(r'19\d{2}', date['text'])
                    if year_match:
                        current_year = year_match.group()

            # Format date as month + year for header (use current year as fallback)
            header_date = extract_month_year(chunk_date, current_year) if chunk_date else ''

            chunks.append({
                'chapter_number': chapter_num,
                'chapter_title': chapter_title,
                'text': chunk_text,
                'date': header_date,
                'dates': chunk_dates_list,
                'places': [{
                    'id': p['id'],
                    'text': p['text'],
                    'display_name': p['display_name'],
                    'geocoded': p['geocoded'],
                } for p in chunk['places']],
            })

    return chunks


def generate_index(data: dict, template_dir: str, output_path: str):
    """Generate the main index.html page."""
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('index.html')

    chunks = build_chunks(data)
    chunks_json = json.dumps(chunks, ensure_ascii=False)

    html = template.render(chunks_json=chunks_json)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Generated: {output_path} ({len(chunks)} chunks)")


def generate_debug(data: dict, template_dir: str, output_path: str):
    """Generate the debug.html correction interface."""
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('debug.html')

    data_json = json.dumps(data, ensure_ascii=False)

    html = template.render(data_json=data_json)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    place_count = len(data.get('all_places', []))
    date_count = len(data.get('all_dates', []))
    print(f"Generated: {output_path} ({place_count} places, {date_count} dates)")


def main():
    data_path = "output/chapters_geocoded.json"
    template_dir = "templates"
    output_dir = "output/webapp"

    print(f"Loading data from: {data_path}")
    data = load_data(data_path)

    generate_index(data, template_dir, os.path.join(output_dir, 'index.html'))
    generate_debug(data, template_dir, os.path.join(output_dir, 'debug.html'))

    print("\nDone!")


if __name__ == "__main__":
    main()
