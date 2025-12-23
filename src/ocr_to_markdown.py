#!/usr/bin/env python3
"""
OCR PDF to Markdown.
Extracts text from PDF and produces a markdown file with chapters as level 2 headings.
"""

import re
import os
import pymupdf

# Roman numeral pattern for chapter detection
ROMAN_PATTERN = r'^([IVXLCDM]+)\.\s*[-–—]\s*(.+?)$'

# Header pattern to remove (page header)
HEADER_PATTERN = r'Historique du 24[èe]me RI.*?numérisé par.*?\n'

# Page number pattern
PAGE_NUMBER_PATTERN = r'\n\s*\d+/\d+\s*\n'


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from PDF."""
    doc = pymupdf.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"
    doc.close()
    return full_text


def clean_text(text: str) -> str:
    """Remove page headers and page numbers."""
    text = re.sub(HEADER_PATTERN, '', text, flags=re.IGNORECASE)
    text = re.sub(PAGE_NUMBER_PATTERN, '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_chapter_content(text: str) -> str:
    """Clean chapter text: merge broken lines within paragraphs."""
    # Merge single newlines (broken lines from PDF)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Normalize multiple spaces to single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Normalize multiple newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, one per line."""
    # Protect common abbreviations from being treated as sentence endings
    abbreviations = [
        r'R\.I\.', r'C\.A\.', r'D\.I\.', r'B\.I\.', r'R\.I\.T\.',
        r'St\.', r'Ste\.', r'M\.', r'Mme\.', r'Mlle\.',
        r'etc\.', r'cf\.', r'env\.',
    ]

    protected = text
    placeholders = {}
    for i, abbr in enumerate(abbreviations):
        placeholder = f"__ABBR{i}__"
        matches = re.findall(abbr, protected)
        for match in matches:
            placeholders[placeholder] = match
        protected = re.sub(abbr, placeholder, protected)

    # Split on sentence-ending punctuation followed by space and uppercase or number
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9\-«"])', protected)

    # Restore abbreviations
    result = []
    for sent in sentences:
        for placeholder, original in placeholders.items():
            sent = sent.replace(placeholder, original)
        sent = sent.strip()
        if sent:
            result.append(sent)

    return result


def format_paragraphs_one_sentence_per_line(text: str) -> str:
    """Format text with one sentence per line, preserving paragraph breaks."""
    paragraphs = text.split('\n\n')
    result_paragraphs = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = split_into_sentences(para)
        result_paragraphs.append('\n'.join(sentences))

    return '\n\n'.join(result_paragraphs)


def extract_chapters(full_text: str) -> list[dict]:
    """Extract chapters from full text."""
    chapters = []
    lines = full_text.split('\n')
    current_chapter = None
    current_content = []
    preamble = []

    for line in lines:
        line_stripped = line.strip()
        match = re.match(ROMAN_PATTERN, line_stripped)

        if match:
            if current_chapter:
                content = '\n'.join(current_content).strip()
                if content:
                    current_chapter['text'] = content
                    chapters.append(current_chapter)
            elif preamble:
                # Save preamble as intro chapter
                chapters.append({
                    'number': None,
                    'title': 'Introduction',
                    'text': '\n'.join(preamble).strip()
                })

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
        else:
            preamble.append(line)

    if current_chapter:
        content = '\n'.join(current_content).strip()
        if content:
            current_chapter['text'] = content
            chapters.append(current_chapter)

    return chapters


def chapters_to_markdown(chapters: list[dict]) -> str:
    """Convert chapters to markdown with ## headings, one sentence per line."""
    lines = []

    for chapter in chapters:
        if chapter['number']:
            heading = f"## {chapter['number']}. {chapter['title']}"
        else:
            heading = f"## {chapter['title']}"

        lines.append(heading)
        lines.append("")

        content = clean_chapter_content(chapter['text'])
        content = format_paragraphs_one_sentence_per_line(content)
        lines.append(content)
        lines.append("")
        lines.append("")

    return '\n'.join(lines)


def process_pdf_to_markdown(pdf_path: str, output_path: str):
    """Main function: PDF to markdown."""
    print(f"Extracting text from: {pdf_path}")

    raw_text = extract_text_from_pdf(pdf_path)
    cleaned_text = clean_text(raw_text)

    chapters = extract_chapters(cleaned_text)
    print(f"Found {len(chapters)} chapters")

    for ch in chapters:
        if ch['number']:
            print(f"  {ch['number']}. {ch['title']}")
        else:
            print(f"  {ch['title']}")

    markdown = chapters_to_markdown(chapters)

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown)

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    pdf_path = "sources/RI-024.pdf"
    output_path = "output/document.md"

    process_pdf_to_markdown(pdf_path, output_path)
