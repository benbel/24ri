#!/usr/bin/env python3
"""
Generate debug HTML for place correction.
Displays one place at a time with context (2 places before/after each mention).
"""

import csv
import json
import os
import re


def load_csv(filepath: str) -> list[dict]:
    """Load geocoded places from CSV."""
    places = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            places.append(row)
    return places


def load_markdown(filepath: str) -> str:
    """Load markdown content."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def extract_place_sequence(markdown: str) -> list[dict]:
    """
    Extract all [[place]] mentions in order from the markdown.
    Returns list of {name, start, end, line_num, context}.
    """
    places = []
    lines = markdown.split('\n')

    for line_num, line in enumerate(lines):
        # Find all [[...]] in this line
        for match in re.finditer(r'\[\[([^\]]+)\]\]', line):
            places.append({
                'name': match.group(1),
                'start': match.start(),
                'end': match.end(),
                'line_num': line_num,
                'line': line,
            })

    return places


def build_place_contexts(place_sequence: list[dict], geocoded: dict) -> dict:
    """
    For each unique place, find all mentions and their context (2 before, 2 after).
    Returns {place_name: [{mention_index, before: [...], after: [...]}]}
    """
    contexts = {}

    for i, mention in enumerate(place_sequence):
        name = mention['name']
        name_lower = name.lower()

        if name_lower not in contexts:
            contexts[name_lower] = {
                'name': name,
                'mentions': [],
                'geocoded': geocoded.get(name_lower, {}),
            }

        # Get 2 before and 2 after
        before = []
        after = []

        for j in range(max(0, i - 2), i):
            p = place_sequence[j]
            before.append({
                'name': p['name'],
                'geocoded': geocoded.get(p['name'].lower(), {}),
            })

        for j in range(i + 1, min(len(place_sequence), i + 3)):
            p = place_sequence[j]
            after.append({
                'name': p['name'],
                'geocoded': geocoded.get(p['name'].lower(), {}),
            })

        contexts[name_lower]['mentions'].append({
            'index': i,
            'line_num': mention['line_num'],
            'before': before,
            'after': after,
        })

    return contexts


def generate_html(places_csv: list[dict], contexts: dict) -> str:
    """Generate the debug HTML."""
    # Build geocoded lookup and places list for JS
    places_list = []
    for row in places_csv:
        name = row['original_name']
        name_lower = name.lower()
        ctx = contexts.get(name_lower, {})

        place_data = {
            'name': name,
            'matched_name': row.get('matched_name', ''),
            'latitude': row.get('latitude', ''),
            'longitude': row.get('longitude', ''),
            'type': row.get('type', ''),
            'score': row.get('score', ''),
            'status': row.get('status', ''),
            'mentions': ctx.get('mentions', []),
        }
        places_list.append(place_data)

    data_json = json.dumps(places_list, ensure_ascii=False)

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Debug - Correction des lieux</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: system-ui, sans-serif; background: #f5f5f5; }}
        #container {{ display: flex; height: 100vh; }}
        #map {{ flex: 1; }}
        #sidebar {{ width: 420px; display: flex; flex-direction: column; background: #fff; border-left: 1px solid #ccc; }}

        #header {{ padding: 12px 16px; background: #333; color: #fff; display: flex; justify-content: space-between; align-items: center; }}
        #header h1 {{ font-size: 14px; font-weight: 600; }}
        #progress {{ font-size: 12px; color: #aaa; }}

        #place-info {{ padding: 16px; border-bottom: 1px solid #ddd; }}
        .place-name {{ font-size: 22px; font-weight: bold; margin-bottom: 8px; }}
        .place-meta {{ font-size: 12px; color: #666; margin-bottom: 4px; }}
        .place-meta.review {{ color: #c84; }}
        .place-meta.not_found {{ color: #c44; }}
        .place-coords {{ font-size: 13px; color: #4a8a6a; font-family: monospace; }}

        #mentions {{ flex: 1; overflow-y: auto; padding: 16px; }}
        .mention {{ background: #f9f9f9; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; margin-bottom: 12px; }}
        .mention-header {{ font-size: 11px; color: #999; margin-bottom: 8px; }}
        .mention-context {{ font-size: 13px; line-height: 1.5; }}
        .mention-context .place {{ background: #e8f4e8; padding: 1px 4px; border-radius: 3px; }}
        .mention-context .place.current {{ background: #4a8a6a; color: #fff; font-weight: bold; }}
        .mention-context .place.before {{ background: #e0e8f0; }}
        .mention-context .place.after {{ background: #f0e8e0; }}

        #correction {{ padding: 16px; background: #f0f0f0; border-top: 1px solid #ddd; }}
        #correction h3 {{ font-size: 12px; color: #666; margin-bottom: 10px; }}
        .correction-row {{ display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }}
        .corr-btn {{ padding: 10px 20px; border: 2px solid #4a8a6a; background: #fff; color: #4a8a6a; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; }}
        .corr-btn:hover {{ background: #f0f8f0; }}
        .corr-btn.active {{ background: #4a8a6a; color: #fff; }}
        .corr-btn.nok {{ border-color: #c44; color: #c44; }}
        .corr-btn.nok:hover {{ background: #fff0f0; }}
        .corr-btn.nok.active {{ background: #c44; color: #fff; }}
        .coords-input {{ flex: 1; padding: 10px; border: 2px solid #ccc; border-radius: 6px; font-size: 14px; font-family: monospace; }}
        .coords-input:focus {{ border-color: #4a8a6a; outline: none; }}
        .coords-input.has-value {{ border-color: #4a8a6a; background: #f0f8f0; }}

        #navigation {{ display: flex; gap: 10px; padding: 16px; background: #fff; border-top: 1px solid #ddd; }}
        .nav-btn {{ flex: 1; padding: 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; }}
        .nav-btn.prev {{ background: #e0e0e0; color: #333; }}
        .nav-btn.next {{ background: #4a8a6a; color: #fff; }}
        .nav-btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}

        #toolbar {{ padding: 12px 16px; background: #333; display: flex; gap: 10px; }}
        .tool-btn {{ padding: 8px 16px; background: #555; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }}
        .tool-btn:hover {{ background: #666; }}

        #filter-bar {{ padding: 10px 16px; background: #fff; border-bottom: 1px solid #ddd; display: flex; gap: 10px; align-items: center; }}
        #filter-bar label {{ font-size: 12px; color: #666; }}
        #filter-bar select {{ padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 12px; }}
    </style>
</head>
<body>
    <div id="container">
        <div id="map"></div>
        <div id="sidebar">
            <div id="header">
                <h1>Correction des lieux</h1>
                <span id="progress">0 / 0</span>
            </div>
            <div id="filter-bar">
                <label>Filtrer:</label>
                <select id="status-filter">
                    <option value="all">Tous</option>
                    <option value="review" selected>A verifier</option>
                    <option value="not_found">Non trouves</option>
                    <option value="found">Valides</option>
                </select>
            </div>
            <div id="place-info">
                <div class="place-name" id="current-name">-</div>
                <div class="place-meta" id="current-meta">-</div>
                <div class="place-coords" id="current-coords">-</div>
            </div>
            <div id="mentions"></div>
            <div id="correction">
                <h3>Correction</h3>
                <div class="correction-row">
                    <button class="corr-btn" id="btn-ok">OK</button>
                    <button class="corr-btn nok" id="btn-nok">NOK</button>
                    <input type="text" class="coords-input" id="coords-input" placeholder="lat, lon (ex: 48.8566, 2.3522)">
                </div>
            </div>
            <div id="navigation">
                <button class="nav-btn prev" id="btn-prev">Precedent</button>
                <button class="nav-btn next" id="btn-next">Suivant</button>
            </div>
            <div id="toolbar">
                <button class="tool-btn" id="btn-export">Exporter CSV</button>
                <button class="tool-btn" id="btn-stats">Stats</button>
            </div>
        </div>
    </div>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const allPlaces = {data_json};

        // Corrections stored in localStorage
        const corrections = JSON.parse(localStorage.getItem('placeCorrections') || '{{}}');

        let filteredPlaces = [];
        let currentIndex = 0;
        let map;
        let markers = [];
        let lines = [];

        function initMap() {{
            map = L.map('map').setView([48.8, 2.5], 6);
            L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
                maxZoom: 18
            }}).addTo(map);
        }}

        function applyFilter() {{
            const filter = document.getElementById('status-filter').value;
            filteredPlaces = allPlaces.filter(p => {{
                // Check if corrected
                const corr = corrections[p.name.toLowerCase()];
                if (corr) {{
                    // If corrected, consider it as "found" for filtering
                    if (filter === 'review' || filter === 'not_found') return false;
                    if (filter === 'found') return true;
                }}
                if (filter === 'all') return true;
                return p.status === filter;
            }});
            currentIndex = 0;
            updateProgress();
            showCurrentPlace();
        }}

        function updateProgress() {{
            const corrected = Object.keys(corrections).length;
            document.getElementById('progress').textContent =
                `${{currentIndex + 1}} / ${{filteredPlaces.length}} (${{corrected}} corriges)`;
        }}

        function getCoords(place) {{
            // Check corrections first
            const corr = corrections[place.name.toLowerCase()];
            if (corr && corr !== 'OK') {{
                const parts = corr.split(',').map(s => parseFloat(s.trim()));
                if (parts.length === 2 && !isNaN(parts[0]) && !isNaN(parts[1])) {{
                    return {{ lat: parts[0], lon: parts[1] }};
                }}
            }}
            // Direct latitude/longitude (main places from allPlaces)
            if (place.latitude && place.longitude) {{
                const lat = parseFloat(place.latitude);
                const lon = parseFloat(place.longitude);
                if (!isNaN(lat) && !isNaN(lon)) {{
                    return {{ lat, lon }};
                }}
            }}
            // Nested geocoded object (before/after places)
            if (place.geocoded && place.geocoded.latitude && place.geocoded.longitude) {{
                const lat = parseFloat(place.geocoded.latitude);
                const lon = parseFloat(place.geocoded.longitude);
                if (!isNaN(lat) && !isNaN(lon)) {{
                    return {{ lat, lon }};
                }}
            }}
            return null;
        }}

        function showCurrentPlace() {{
            if (filteredPlaces.length === 0) {{
                document.getElementById('current-name').textContent = 'Aucun lieu a afficher';
                document.getElementById('current-meta').textContent = '';
                document.getElementById('current-coords').textContent = '';
                document.getElementById('mentions').innerHTML = '';
                clearMap();
                return;
            }}

            const place = filteredPlaces[currentIndex];
            const corr = corrections[place.name.toLowerCase()];

            // Update info
            document.getElementById('current-name').textContent = place.name;

            const meta = document.getElementById('current-meta');
            meta.textContent = `${{place.matched_name}} (${{place.type}}, score: ${{parseFloat(place.score || 0).toFixed(2)}})`;
            meta.className = 'place-meta ' + place.status;

            const coords = getCoords(place);
            document.getElementById('current-coords').textContent = coords
                ? `${{coords.lat.toFixed(5)}}, ${{coords.lon.toFixed(5)}}`
                : 'Pas de coordonnees';

            // Update correction UI
            updateCorrectionUI(place);

            // Show mentions
            showMentions(place);

            // Update map
            updateMap(place);

            // Update navigation
            document.getElementById('btn-prev').disabled = currentIndex === 0;
            document.getElementById('btn-next').disabled = currentIndex >= filteredPlaces.length - 1;

            updateProgress();
        }}

        function showMentions(place) {{
            const container = document.getElementById('mentions');

            if (!place.mentions || place.mentions.length === 0) {{
                container.innerHTML = '<p style="color:#999;padding:20px;">Aucune mention trouvee</p>';
                return;
            }}

            container.innerHTML = place.mentions.map((m, i) => {{
                // Build context display
                let contextHtml = '';

                m.before.forEach(p => {{
                    contextHtml += `<span class="place before">${{escapeHtml(p.name)}}</span> ... `;
                }});

                contextHtml += `<span class="place current">${{escapeHtml(place.name)}}</span>`;

                m.after.forEach(p => {{
                    contextHtml += ` ... <span class="place after">${{escapeHtml(p.name)}}</span>`;
                }});

                return `
                    <div class="mention" data-mention="${{i}}">
                        <div class="mention-header">Mention ${{i + 1}} (ligne ${{m.line_num + 1}})</div>
                        <div class="mention-context">${{contextHtml}}</div>
                    </div>
                `;
            }}).join('');
        }}

        function escapeHtml(text) {{
            return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }}

        function clearMap() {{
            markers.forEach(m => map.removeLayer(m));
            lines.forEach(l => map.removeLayer(l));
            markers = [];
            lines = [];
        }}

        function updateMap(place) {{
            clearMap();

            if (!place.mentions || place.mentions.length === 0) return;

            const bounds = [];
            const colors = {{
                before: '#3388ff',
                current: '#dc3545',
                after: '#28a745'
            }};

            place.mentions.forEach((mention, mentionIdx) => {{
                const segmentPoints = [];

                // Before places
                mention.before.forEach(p => {{
                    const c = getCoords(p);
                    if (c) {{
                        segmentPoints.push({{ ...c, type: 'before', name: p.name }});
                        bounds.push([c.lat, c.lon]);
                    }}
                }});

                // Current place
                const currentCoords = getCoords(place);
                if (currentCoords) {{
                    segmentPoints.push({{ ...currentCoords, type: 'current', name: place.name }});
                    bounds.push([currentCoords.lat, currentCoords.lon]);
                }}

                // After places
                mention.after.forEach(p => {{
                    const c = getCoords(p);
                    if (c) {{
                        segmentPoints.push({{ ...c, type: 'after', name: p.name }});
                        bounds.push([c.lat, c.lon]);
                    }}
                }});

                // Draw line connecting all points
                if (segmentPoints.length > 1) {{
                    const lineCoords = segmentPoints.map(p => [p.lat, p.lon]);
                    const line = L.polyline(lineCoords, {{
                        color: '#666',
                        weight: 2,
                        opacity: 0.6,
                        dashArray: '5, 5'
                    }}).addTo(map);
                    lines.push(line);
                }}

                // Add markers
                segmentPoints.forEach((p, idx) => {{
                    const marker = L.circleMarker([p.lat, p.lon], {{
                        radius: p.type === 'current' ? 12 : 8,
                        fillColor: colors[p.type],
                        color: '#fff',
                        weight: 2,
                        fillOpacity: 0.9
                    }}).addTo(map);

                    marker.bindTooltip(p.name, {{ direction: 'top', permanent: p.type === 'current' }});
                    markers.push(marker);
                }});
            }});

            // Fit bounds
            if (bounds.length > 0) {{
                if (bounds.length === 1) {{
                    map.setView(bounds[0], 10);
                }} else {{
                    map.fitBounds(bounds, {{ padding: [50, 50], maxZoom: 12 }});
                }}
            }}
        }}

        function saveCorrection(value) {{
            if (filteredPlaces.length === 0) return;
            const place = filteredPlaces[currentIndex];
            corrections[place.name.toLowerCase()] = value;
            localStorage.setItem('placeCorrections', JSON.stringify(corrections));
            // Update UI and map
            updateCorrectionUI(place);
            updateMap(place);
        }}

        function updateCorrectionUI(place) {{
            const corr = corrections[place.name.toLowerCase()];
            const okBtn = document.getElementById('btn-ok');
            const nokBtn = document.getElementById('btn-nok');
            const coordsInput = document.getElementById('coords-input');

            okBtn.classList.remove('active');
            nokBtn.classList.remove('active');
            coordsInput.classList.remove('has-value');

            if (corr === 'OK') {{
                okBtn.classList.add('active');
                coordsInput.value = '';
            }} else if (corr === 'NOK') {{
                nokBtn.classList.add('active');
                coordsInput.value = '';
            }} else if (corr) {{
                coordsInput.value = corr;
                coordsInput.classList.add('has-value');
            }} else {{
                coordsInput.value = '';
            }}

            // Update displayed coordinates
            const coords = getCoords(place);
            document.getElementById('current-coords').textContent = coords
                ? `${{coords.lat.toFixed(5)}}, ${{coords.lon.toFixed(5)}}`
                : 'Pas de coordonnees';
        }}

        function goNext() {{
            if (currentIndex < filteredPlaces.length - 1) {{
                currentIndex++;
                showCurrentPlace();
            }}
        }}

        function goPrev() {{
            if (currentIndex > 0) {{
                currentIndex--;
                showCurrentPlace();
            }}
        }}

        function exportCSV() {{
            let csv = 'original_name,matched_name,latitude,longitude,type,score,status,correction\\n';

            allPlaces.forEach(p => {{
                const corr = corrections[p.name.toLowerCase()] || '';
                let lat = p.latitude || '';
                let lon = p.longitude || '';
                let status = p.status;

                // Handle different correction types
                if (corr === 'NOK') {{
                    status = 'excluded';
                    lat = '';
                    lon = '';
                }} else if (corr && corr !== 'OK') {{
                    // Correction is coordinates
                    const parts = corr.split(',').map(s => s.trim());
                    if (parts.length === 2) {{
                        lat = parts[0];
                        lon = parts[1];
                        status = 'corrected';
                    }}
                }} else if (corr === 'OK') {{
                    status = 'validated';
                }}

                csv += `"${{p.name.replace(/"/g, '""')}}","${{(p.matched_name || '').replace(/"/g, '""')}}",${{lat}},${{lon}},"${{p.type || ''}}",${{p.score || ''}},${{status}},"${{corr}}"\\n`;
            }});

            const blob = new Blob([csv], {{ type: 'text/csv' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'places_corrected.csv';
            a.click();
            URL.revokeObjectURL(url);
        }}

        function showStats() {{
            const total = allPlaces.length;
            const corrected = Object.keys(corrections).length;
            const ok = Object.values(corrections).filter(v => v === 'OK').length;
            const nok = Object.values(corrections).filter(v => v === 'NOK').length;
            const withCoords = Object.values(corrections).filter(v => v && v !== 'OK' && v !== 'NOK').length;

            const review = allPlaces.filter(p => p.status === 'review').length;
            const notFound = allPlaces.filter(p => p.status === 'not_found').length;
            const found = allPlaces.filter(p => p.status === 'found').length;

            alert(`Statistiques:
- Total: ${{total}} lieux
- Valides automatiquement: ${{found}}
- A verifier: ${{review}}
- Non trouves: ${{notFound}}

Corrections effectuees: ${{corrected}}
- Marques OK: ${{ok}}
- Marques NOK: ${{nok}}
- Avec nouvelles coordonnees: ${{withCoords}}`);
        }}

        // Event listeners
        document.getElementById('status-filter').onchange = applyFilter;
        document.getElementById('btn-ok').onclick = () => saveCorrection('OK');
        document.getElementById('btn-nok').onclick = () => saveCorrection('NOK');
        document.getElementById('coords-input').oninput = (e) => {{
            const val = e.target.value.trim();
            if (val) {{
                // Temporarily save to see the update on the map
                const place = filteredPlaces[currentIndex];
                if (place) {{
                    corrections[place.name.toLowerCase()] = val;
                    updateMap(place);
                    // Update coord display
                    const coords = getCoords(place);
                    document.getElementById('current-coords').textContent = coords
                        ? `${{coords.lat.toFixed(5)}}, ${{coords.lon.toFixed(5)}}`
                        : 'Pas de coordonnees';
                    e.target.classList.add('has-value');
                }}
            }}
        }};
        document.getElementById('coords-input').onchange = (e) => {{
            const val = e.target.value.trim();
            if (val) {{
                saveCorrection(val);
            }}
        }};
        document.getElementById('btn-prev').onclick = goPrev;
        document.getElementById('btn-next').onclick = goNext;
        document.getElementById('btn-export').onclick = exportCSV;
        document.getElementById('btn-stats').onclick = showStats;

        // Keyboard navigation
        document.addEventListener('keydown', (e) => {{
            if (e.target.tagName === 'INPUT') return;
            if (e.key === 'ArrowRight' || e.key === 'n') goNext();
            if (e.key === 'ArrowLeft' || e.key === 'p') goPrev();
            if (e.key === 'o') {{ saveCorrection('OK'); goNext(); }}
            if (e.key === 'x') {{ saveCorrection('NOK'); goNext(); }}
        }});

        // Initialize
        document.addEventListener('DOMContentLoaded', () => {{
            initMap();
            applyFilter();
        }});
    </script>
</body>
</html>'''

    return html


def main():
    # Input files
    csv_manual = "manual_modifications/places_geocoded.csv"
    csv_default = "output/places_geocoded.csv"
    md_manual = "manual_modifications/ner_document.md"
    md_default = "output/ner_document.md"
    output_path = "output/debug.html"

    # Find CSV
    if os.path.exists(csv_manual):
        csv_path = csv_manual
        print(f"Using CSV: {csv_manual}")
    elif os.path.exists(csv_default):
        csv_path = csv_default
        print(f"Using CSV: {csv_default}")
    else:
        print("Error: No places_geocoded.csv found")
        return

    # Find markdown
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
    places_csv = load_csv(csv_path)
    print(f"Loaded {len(places_csv)} places from CSV")

    markdown = load_markdown(md_path)
    place_sequence = extract_place_sequence(markdown)
    print(f"Found {len(place_sequence)} place mentions in markdown")

    # Build geocoded lookup
    geocoded = {}
    for row in places_csv:
        name_lower = row['original_name'].lower()
        geocoded[name_lower] = row

    # Build contexts
    contexts = build_place_contexts(place_sequence, geocoded)
    print(f"Built contexts for {len(contexts)} unique places")

    # Generate HTML
    html = generate_html(places_csv, contexts)

    # Save
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
