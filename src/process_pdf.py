#!/usr/bin/env python3
"""
PDF Processing Script for 24e RI Historical Document.
Extracts chapters, applies NER for places and dates using spacy fr_core_news_lg.
Assigns unique IDs to all NER entities and generates YAML correction files.
"""

import json
import re
import os
import uuid
import pymupdf
import spacy
import yaml
from spacy.matcher import Matcher

# Load French NER model (large)
nlp = spacy.load("fr_core_news_lg")

# Setup date matcher (fr_core_news_lg doesn't detect dates natively)
matcher = Matcher(nlp.vocab)

MONTHS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin',
          'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']

# Date patterns for the matcher
date_patterns = [
    [{"IS_DIGIT": True}, {"LOWER": {"IN": MONTHS}}, {"SHAPE": "dddd"}],  # 17 mai 1917
    [{"IS_DIGIT": True}, {"LOWER": {"IN": MONTHS}}],  # 17 mai
    [{"LOWER": {"IN": MONTHS}}, {"SHAPE": "dddd"}],  # mai 1917
]

for i, pattern in enumerate(date_patterns):
    matcher.add(f"DATE_{i}", [pattern])

# Roman numeral pattern for chapter detection
ROMAN_PATTERN = r'^([IVXLCDM]+)\.\s*[-–—]\s*(.+?)$'

# Header pattern to remove (page header)
HEADER_PATTERN = r'Historique du 24[èe]me RI.*?numérisé par.*?\n'

# Page number pattern
PAGE_NUMBER_PATTERN = r'\n\s*\d+/\d+\s*\n'


def generate_id() -> str:
    """Generate a short unique ID."""
    return uuid.uuid4().hex[:8]


def clean_text_basic(text: str) -> str:
    """Remove cruft like page headers and page numbers, keeping newlines for chapter detection."""
    text = re.sub(HEADER_PATTERN, '', text, flags=re.IGNORECASE)
    text = re.sub(PAGE_NUMBER_PATTERN, '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_chapter_text(text: str) -> str:
    """Clean chapter text by removing extra newlines within paragraphs."""
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def extract_chapters(full_text: str) -> list[dict]:
    """Extract chapters from the full text."""
    chapters = []
    lines = full_text.split('\n')
    current_chapter = None
    current_content = []

    for line in lines:
        line_stripped = line.strip()
        match = re.match(ROMAN_PATTERN, line_stripped)

        if match:
            if current_chapter:
                content = '\n'.join(current_content).strip()
                if content:
                    current_chapter['text'] = content
                    chapters.append(current_chapter)

            roman_num = match.group(1)
            title = match.group(2).strip()
            current_chapter = {
                'number': roman_num,
                'title': title,
                'text': ''
            }
            current_content = []
        elif current_chapter:
            current_content.append(line)

    if current_chapter:
        content = '\n'.join(current_content).strip()
        if content:
            current_chapter['text'] = content
            chapters.append(current_chapter)

    return chapters


def extract_paragraphs(text: str) -> list[dict]:
    """Split text into paragraphs with their positions."""
    paragraphs = []
    current_pos = 0

    for para in text.split('\n\n'):
        para = para.strip()
        if para:
            start = text.find(para, current_pos)
            paragraphs.append({
                'text': para,
                'start': start,
                'end': start + len(para)
            })
            current_pos = start + len(para)

    return paragraphs


def extract_entities_with_ner(text: str) -> tuple[list[dict], list[dict]]:
    """
    Extract places (LOC) using spacy NER and dates using Matcher.
    Returns (places, dates) with unique IDs.
    """
    doc = nlp(text)
    places = []
    dates = []

    # Extract LOC entities
    for ent in doc.ents:
        if ent.label_ == 'LOC':
            if len(ent.text.strip()) >= 2:
                places.append({
                    'id': generate_id(),
                    'text': ent.text.strip(),
                    'start': ent.start_char,
                    'end': ent.end_char,
                    'label': 'LOC',
                    'sentence': ent.sent.text.strip() if ent.sent else '',
                    'sentence_start': ent.sent.start_char if ent.sent else ent.start_char,
                    'sentence_end': ent.sent.end_char if ent.sent else ent.end_char,
                })

    # Extract dates using Matcher
    matches = matcher(doc)
    seen_spans = set()

    for match_id, start, end in matches:
        span = doc[start:end]
        span_key = (span.start_char, span.end_char)

        if span_key in seen_spans:
            continue
        seen_spans.add(span_key)

        date_text = span.text.strip()
        sent = span.sent

        dates.append({
            'id': generate_id(),
            'text': date_text,
            'start': span.start_char,
            'end': span.end_char,
            'label': 'DATE',
            'sentence': sent.text.strip() if sent else '',
            'sentence_start': sent.start_char if sent else span.start_char,
            'sentence_end': sent.end_char if sent else span.end_char,
        })

    places.sort(key=lambda x: x['start'])
    dates.sort(key=lambda x: x['start'])

    return places, dates


def find_paragraph_for_entity(entity: dict, paragraphs: list[dict]) -> dict | None:
    """Find which paragraph contains this entity."""
    for para in paragraphs:
        if para['start'] <= entity['start'] < para['end']:
            return para
    return None


def create_segments(text: str, places: list[dict], dates: list[dict], paragraphs: list[dict]) -> list[dict]:
    """Create segments grouping sentences with their places and dates."""
    segments = []
    sentence_map = {}

    for place in places:
        key = (place['sentence_start'], place['sentence_end'])
        if key not in sentence_map:
            sentence_map[key] = {
                'sentence': place['sentence'],
                'sentence_start': place['sentence_start'],
                'sentence_end': place['sentence_end'],
                'places': [],
                'dates': [],
                'paragraph': find_paragraph_for_entity(place, paragraphs),
            }
        sentence_map[key]['places'].append(place)

    for date in dates:
        key = (date['sentence_start'], date['sentence_end'])
        if key in sentence_map:
            sentence_map[key]['dates'].append(date)

    segments = sorted(sentence_map.values(), key=lambda x: x['sentence_start'])
    return segments


def generate_correction_files(all_places: list[dict], all_dates: list[dict], corrections_dir: str):
    """Generate YAML correction files pre-filled with OK values."""
    os.makedirs(corrections_dir, exist_ok=True)

    # Places corrections
    places_corrections = {}
    for place in all_places:
        places_corrections[place['id']] = {
            'original': place['text'],
            'correction': 'OK'
        }

    places_path = os.path.join(corrections_dir, 'places_corrections.yaml')
    with open(places_path, 'w', encoding='utf-8') as f:
        yaml.dump(places_corrections, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  Saved: {places_path} ({len(places_corrections)} entries)")

    # Dates corrections
    dates_corrections = {}
    for date in all_dates:
        dates_corrections[date['id']] = {
            'original': date['text'],
            'correction': 'OK'
        }

    dates_path = os.path.join(corrections_dir, 'dates_corrections.yaml')
    with open(dates_path, 'w', encoding='utf-8') as f:
        yaml.dump(dates_corrections, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  Saved: {dates_path} ({len(dates_corrections)} entries)")


def process_pdf(pdf_path: str, output_path: str, corrections_dir: str):
    """Main processing function."""
    print(f"Processing PDF: {pdf_path}")

    doc = pymupdf.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()

    cleaned_text = clean_text_basic(full_text)
    chapters = extract_chapters(cleaned_text)
    print(f"Found {len(chapters)} chapters")

    for chapter in chapters:
        chapter['text'] = clean_chapter_text(chapter['text'])

    all_places = []
    all_dates = []
    global_place_order = 0
    global_date_order = 0

    for chapter in chapters:
        text = chapter['text']

        paragraphs = extract_paragraphs(text)
        chapter['paragraphs'] = paragraphs

        places, dates = extract_entities_with_ner(text)
        segments = create_segments(text, places, dates, paragraphs)

        for p in places:
            p['chapter'] = chapter['number']
            p['chapter_title'] = chapter['title']
            p['global_order'] = global_place_order
            global_place_order += 1
            all_places.append(p)

        for d in dates:
            d['chapter'] = chapter['number']
            d['chapter_title'] = chapter['title']
            d['global_order'] = global_date_order
            global_date_order += 1
            all_dates.append(d)

        chapter['places'] = places
        chapter['dates'] = dates
        chapter['segments'] = segments

        print(f"  Chapter {chapter['number']}: {chapter['title']}")
        print(f"    Places: {len(places)}, Dates: {len(dates)}, Segments: {len(segments)}")

    # Generate correction files
    generate_correction_files(all_places, all_dates, corrections_dir)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    output_data = {
        'chapters': chapters,
        'all_places': all_places,
        'all_dates': all_dates,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")
    print(f"Total places: {len(all_places)}, Total dates: {len(all_dates)}")
    return output_data


if __name__ == "__main__":
    pdf_path = "sources/RI-024.pdf"
    output_path = "output/chapters.json"
    corrections_dir = "output/corrections"

    process_pdf(pdf_path, output_path, corrections_dir)
