#!/usr/bin/env python3
"""
NER Processing for Markdown Document.
Takes a markdown file and annotates places with [[X]] and dates with {{Y}}.
"""

import re
import os
import spacy
from spacy.matcher import Matcher

# Load French NER model (large)
print("Loading spacy model...")
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


def extract_entities(text: str) -> tuple[list[dict], list[dict]]:
    """
    Extract places (LOC) using spacy NER and dates using Matcher.
    Returns (places, dates) with start/end positions.
    """
    doc = nlp(text)
    places = []
    dates = []

    # Extract LOC entities
    for ent in doc.ents:
        if ent.label_ == 'LOC':
            if len(ent.text.strip()) >= 2:
                places.append({
                    'text': ent.text.strip(),
                    'start': ent.start_char,
                    'end': ent.end_char,
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

        dates.append({
            'text': span.text.strip(),
            'start': span.start_char,
            'end': span.end_char,
        })

    return places, dates


def annotate_text(text: str, places: list[dict], dates: list[dict]) -> str:
    """
    Insert [[place]] and {{date}} markers into text.
    Process in reverse order to preserve positions.
    """
    # Combine all entities with their marker type
    entities = []
    for p in places:
        entities.append({**p, 'type': 'place'})
    for d in dates:
        entities.append({**d, 'type': 'date'})

    # Remove overlapping entities (keep the longer one)
    entities.sort(key=lambda x: (x['start'], -x['end']))
    filtered = []
    last_end = -1
    for ent in entities:
        if ent['start'] >= last_end:
            filtered.append(ent)
            last_end = ent['end']

    # Sort by position descending to insert from end
    filtered.sort(key=lambda x: x['start'], reverse=True)

    # Insert markers
    result = text
    for ent in filtered:
        start, end = ent['start'], ent['end']
        original = result[start:end]

        if ent['type'] == 'place':
            marked = f"[[{original}]]"
        else:
            marked = f"{{{{{original}}}}}"

        result = result[:start] + marked + result[end:]

    return result


def process_line(line: str) -> str:
    """Process a single line, skipping markdown headings."""
    # Skip headings (## ...)
    if line.startswith('#'):
        return line

    # Skip empty lines
    if not line.strip():
        return line

    # Extract entities and annotate
    places, dates = extract_entities(line)
    if places or dates:
        return annotate_text(line, places, dates)

    return line


def process_markdown(input_path: str, output_path: str):
    """Process markdown file with NER annotations."""
    print(f"Reading: {input_path}")

    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    total_places = 0
    total_dates = 0

    processed_lines = []
    for line in lines:
        processed = process_line(line)
        processed_lines.append(processed)

        # Count entities for stats
        total_places += processed.count('[[')
        total_dates += processed.count('{{')

    result = '\n'.join(processed_lines)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)

    print(f"Saved to: {output_path}")
    print(f"Total places annotated: {total_places}")
    print(f"Total dates annotated: {total_dates}")


def main():
    # Check for manual modifications first
    manual_path = "manual_modifications/document.md"
    default_path = "output/document.md"
    output_path = "output/ner_document.md"

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

    process_markdown(input_path, output_path)


if __name__ == "__main__":
    main()
