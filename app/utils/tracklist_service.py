"""
Gets a tracklist from a search query.

Args:
    query: The search query to look for

Returns:
    Dict: Dictionary containing the search results with detailed track information
"""

import asyncio
import json
from typing import Dict, Any

import redis
import os
from datetime import timedelta

from .tracklist_parser import extract_tracks_simple
from .tracklist_html import get_html_from_results
from .mixesdb import search
from .query_utils import extract_query_without_by
from .result_matcher import find_best_match

# Cache TTL in seconds (24 hours)
CACHE_TTL = 24 * 60 * 60

# Initialize Redis client with Render Key Value service
redis_client = None
try:
    # Try REDIS_URL first (Render may provide this as a connection string)
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        # Parse Redis URL (format: redis://[:password@]host[:port][/db])
        redis_client = redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=10,  # 10 second timeout for operations
            socket_connect_timeout=10  # 10 second timeout for connections
        )
    else:
        # Fall back to REDIS_HOST and REDIS_PORT
        redis_host = os.getenv('REDIS_HOST')
        redis_port = os.getenv('REDIS_PORT', '6379')

        if redis_host:
            redis_client = redis.Redis(
                host=redis_host,
                port=int(redis_port),
                decode_responses=True,
                socket_timeout=10,  # 10 second timeout for operations
                socket_connect_timeout=10  # 10 second timeout for connections
            )

    if redis_client:
        # Test connection
        redis_client.ping()
except (redis.ConnectionError, redis.TimeoutError):
    redis_client = None
except Exception:
    redis_client = None


async def get_tracks(query: str = "job jobse") -> Dict[str, Any]:
    # Check cache first if available
    if redis_client:
        try:
            cache_key = f"tracklist:{query}"
            cached_result = redis_client.get(cache_key)
            if cached_result:
                try:
                    return json.loads(cached_result)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    try:
        # Search for tracklists
        results = search(query)

        # If no results found and query contains "by", try without the "by" clause
        if not results:
            fallback_query = extract_query_without_by(query)
            if fallback_query != query:
                results = search(fallback_query)

        if not results:
            print("Query result not found")
            return {"success": True, "tracks": []}

        print("Query result found")

        # Find the best matching result using fuzzy matching
        best_match = find_best_match(query, results, min_score=50.0)
        if not best_match:
            print("Query result not found")
            return {"success": True, "results": []}

        # Get HTML content from the best matching result only
        html_entries = get_html_from_results([best_match])

        if not html_entries:
            print("Query result not found")
            return {"success": True, "results": []}

        # Parse tracks from each HTML entry
        print("Extracting tracks...")
        parsed_results = []
        for entry in html_entries:
            title = entry.get("title", "")
            url = entry.get("url", "")
            html = entry.get("html")
            match_score = best_match.get("match_score")

            if not html:
                parsed_results.append({
                    "title": title,
                    "url": url,
                    "tracks": [],
                    "match_score": match_score
                })
                continue

            # Parse tracks from this HTML
            try:
                tracks_json = extract_tracks_simple(html)
                if tracks_json == "no tracklist":
                    tracks = []
                else:
                    tracks = json.loads(tracks_json)

                parsed_results.append({
                    "title": title,
                    "url": url,
                    "tracks": tracks,
                    "match_score": match_score
                })
            except Exception:
                parsed_results.append({
                    "title": title,
                    "url": url,
                    "tracks": [],
                    "match_score": match_score
                })

        print("Successfully extracted tracks")

        result = {
            "success": True,
            "results": parsed_results,
        }

        # Cache the result if Redis is available
        if redis_client:
            try:
                cache_key = f"tracklist:{query}"
                redis_client.setex(
                    cache_key,
                    CACHE_TTL,
                    json.dumps(result)
                )
            except Exception:
                pass

        return result

    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse track data: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


if __name__ == "__main__":
    asyncio.run(get_tracks())

