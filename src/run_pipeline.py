#!/usr/bin/env python3
"""
Orchestration script for the 24RI document processing pipeline.
Runs all steps in order with manual intervention points.

Usage:
    python run_pipeline.py          # Interactive mode (asks for confirmations)
    python run_pipeline.py --auto   # Automatic mode (skips confirmations, uses existing files)
"""

import argparse
import os
import subprocess
import sys
import shutil

# Parse command line arguments
parser = argparse.ArgumentParser(description='24RI Document Processing Pipeline')
parser.add_argument('--auto', action='store_true',
                    help='Run in automatic mode (skip confirmations, use existing files)')
args = parser.parse_args()

# Define colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text: str):
    """Print a formatted header."""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_step(step_num: int, text: str):
    """Print a step indicator."""
    print(f"{Colors.BLUE}{Colors.BOLD}[Step {step_num}] {text}{Colors.ENDC}")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}{text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}{text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}{text}{Colors.ENDC}")


def run_script(script_name: str) -> bool:
    """Run a Python script and return success status."""
    script_path = os.path.join("src", script_name)
    print(f"Running: python3 {script_path}")
    print("-" * 40)

    result = subprocess.run([sys.executable, script_path])

    print("-" * 40)
    return result.returncode == 0


def wait_for_confirmation(message: str) -> bool:
    """Wait for user confirmation. Returns True to continue, False to abort."""
    print()
    print_warning(message)

    # In auto mode, always continue
    if args.auto:
        print(f"{Colors.BOLD}[AUTO] Continuing...{Colors.ENDC}")
        return True

    while True:
        response = input(f"{Colors.BOLD}Continue? [y/n/skip]: {Colors.ENDC}").strip().lower()
        if response in ['y', 'yes', 'o', 'oui']:
            return True
        elif response in ['n', 'no', 'non']:
            return False
        elif response in ['skip', 's']:
            return 'skip'
        else:
            print("Please enter 'y' to continue, 'n' to abort, or 'skip' to skip this step.")


def check_file_exists(filepath: str) -> bool:
    """Check if a file exists and print status."""
    if os.path.exists(filepath):
        print_success(f"  Found: {filepath}")
        return True
    else:
        print_warning(f"  Not found: {filepath}")
        return False


def ensure_directories():
    """Ensure output directories exist."""
    os.makedirs("output", exist_ok=True)
    os.makedirs("output/webapp", exist_ok=True)
    os.makedirs("manual_modifications", exist_ok=True)


def main():
    print_header("24RI Document Processing Pipeline")

    ensure_directories()

    # =========================================================================
    # STEP 1: OCR PDF to Markdown
    # =========================================================================
    print_step(1, "OCR PDF to Markdown")

    # Check if we should skip (manual file already exists)
    if os.path.exists("manual_modifications/document.md"):
        print_success("Manual markdown file already exists.")
        response = wait_for_confirmation(
            "manual_modifications/document.md exists. Skip OCR step?"
        )
        if response == 'skip' or response == True:
            print("Skipping OCR step.")
        elif response == False:
            print("Aborted by user.")
            return
    else:
        if not run_script("ocr_to_markdown.py"):
            print_error("OCR step failed!")
            return

        print()
        print_success("OCR complete. Output: output/document.md")
        print()
        print("Please review and correct the markdown file:")
        print(f"  1. Copy {Colors.BOLD}output/document.md{Colors.ENDC} to {Colors.BOLD}manual_modifications/document.md{Colors.ENDC}")
        print("  2. Correct any OCR errors")
        print("  3. Ensure chapters are properly detected (## headings)")
        print("  4. Ensure one sentence per line")

        response = wait_for_confirmation("Have you finished correcting the markdown?")
        if response == False:
            print("Aborted by user.")
            return

    # =========================================================================
    # STEP 2: Named Entity Recognition
    # =========================================================================
    print_step(2, "Named Entity Recognition (NER)")

    # Check if we should skip
    if os.path.exists("manual_modifications/ner_document.md"):
        print_success("Manual NER file already exists.")
        response = wait_for_confirmation(
            "manual_modifications/ner_document.md exists. Skip NER step?"
        )
        if response == 'skip' or response == True:
            print("Skipping NER step.")
        elif response == False:
            print("Aborted by user.")
            return
    else:
        if not run_script("ner_markdown.py"):
            print_error("NER step failed!")
            return

        print()
        print_success("NER complete. Output: output/ner_document.md")
        print()
        print("Please review and correct the NER annotations:")
        print(f"  1. Copy {Colors.BOLD}output/ner_document.md{Colors.ENDC} to {Colors.BOLD}manual_modifications/ner_document.md{Colors.ENDC}")
        print("  2. Add missing place names with [[place]]")
        print("  3. Add missing dates with {{date}}")
        print("  4. Remove false positives")

        response = wait_for_confirmation("Have you finished correcting the NER annotations?")
        if response == False:
            print("Aborted by user.")
            return

    # =========================================================================
    # STEP 3: Geocode Places
    # =========================================================================
    print_step(3, "Geocode Places")

    if not run_script("geocode_places_from_markdown.py"):
        print_error("Geocoding step failed!")
        return

    print()
    print_success("Geocoding complete. Output: output/places_geocoded.csv")

    # =========================================================================
    # STEP 4: Generate Debug HTML
    # =========================================================================
    print_step(4, "Generate Debug HTML for Place Corrections")

    if not run_script("generate_debug_html.py"):
        print_error("Debug HTML generation failed!")
        return

    print()
    print_success("Debug HTML generated: output/debug.html")
    print()
    print("Please review and correct place coordinates:")
    print(f"  1. Open {Colors.BOLD}output/debug.html{Colors.ENDC} in your browser")
    print("  2. For each place:")
    print("     - Click OK if coordinates are correct")
    print("     - Enter new coordinates if needed")
    print("     - Click NOK to exclude the place")
    print("  3. Click 'Download CSV' when done")
    print(f"  4. Save as {Colors.BOLD}manual_modifications/places_corrected.csv{Colors.ENDC}")

    response = wait_for_confirmation("Have you finished correcting the place coordinates?")
    if response == False:
        print("Aborted by user.")
        return

    # =========================================================================
    # STEP 5: Generate Final Places CSV
    # =========================================================================
    print_step(5, "Generate Final Places CSV")

    if not run_script("generate_final_places.py"):
        print_error("Final places generation failed!")
        return

    print()
    print_success("Final places generated: output/places_final.csv")

    # =========================================================================
    # STEP 6: Generate Chunks JSON
    # =========================================================================
    print_step(6, "Generate Chunks JSON")

    if not run_script("generate_chunks_json.py"):
        print_error("Chunks JSON generation failed!")
        return

    print()
    print_success("Chunks JSON generated: output/chunks.json")
    print()
    print("Optionally, you can review and correct the chunks:")
    print(f"  1. Copy {Colors.BOLD}output/chunks.json{Colors.ENDC} to {Colors.BOLD}manual_modifications/chunks.json{Colors.ENDC}")
    print("  2. Adjust chunk boundaries if needed")
    print("  3. Fix date ranges if needed")

    response = wait_for_confirmation("Continue to webpage generation?")
    if response == False:
        print("Aborted by user.")
        return

    # =========================================================================
    # STEP 7: Generate Webpage
    # =========================================================================
    print_step(7, "Generate Final Webpage")

    if not run_script("generate_webpage.py"):
        print_error("Webpage generation failed!")
        return

    print()
    print_success("Webpage generated: output/webapp/index.html")

    # =========================================================================
    # DONE
    # =========================================================================
    print_header("Pipeline Complete!")

    print("Generated files:")
    check_file_exists("output/document.md")
    check_file_exists("output/ner_document.md")
    check_file_exists("output/places_geocoded.csv")
    check_file_exists("output/debug.html")
    check_file_exists("output/places_final.csv")
    check_file_exists("output/chunks.json")
    check_file_exists("output/webapp/index.html")

    print()
    print(f"Open {Colors.BOLD}output/webapp/index.html{Colors.ENDC} in your browser to view the result.")
    print()


if __name__ == "__main__":
    main()
