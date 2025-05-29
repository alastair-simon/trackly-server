"""
Music Track Extractor

This module provides functions to extract track information from HTML
"""

from bs4 import BeautifulSoup
import json
from typing import Dict, Optional
import uuid

def extract_track_from_list_item(text: str) -> Optional[Dict]:
    import re

    # Remove timestamp pattern [XX] from the start
    clean_text = re.sub(r'^\[\d+\]\s*', '', text).strip()

    # Skip if empty or just a question mark
    if not clean_text or clean_text == "?":
        return None

    # Split on first " - " to separate artist and track
    parts = clean_text.split(" - ", 1)
    if len(parts) != 2:
        return None

    # Remove all text between square brackets from both artist and track
    artist = re.sub(r'\[(.*?)\]', '', parts[0]).strip()
    track = re.sub(r'\[(.*?)\]', '', parts[1]).strip()

    return {
        "id": str(uuid.uuid4()),
        "artist": artist,
        "track": track
    }

def extract_tracks_simple(html_content: str) -> str:
    soup = BeautifulSoup(html_content, 'html.parser')
    tracks = []

    # Find the ordered list containing the tracklist
    tracklist = soup.find('ol')
    if not tracklist:
        return "no tracklist"

    # Process each list item
    for li in tracklist.find_all('li'):
        text = li.get_text().strip()
        track = extract_track_from_list_item(text)
        if track:
            tracks.append(track)

    if not tracks:
        return "no tracklist"

    return json.dumps(tracks)