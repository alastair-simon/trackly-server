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
import logging

from .tracklist_parser import extract_tracks_simple
from .tracklist_html import get_html_from_results
from .mixesdb import search
from .query_utils import extract_query_without_by
from .result_matcher import find_best_match

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache TTL in seconds (24 hours)
CACHE_TTL = 24 * 60 * 60

# Initialize Redis client with Render Key Value service
redis_client = None
try:
    redis_host = os.getenv('REDIS_HOST')
    redis_port = os.getenv('REDIS_PORT', '6379')

    if redis_host:
        redis_client = redis.Redis(
            host=redis_host,
            port=int(redis_port),
            decode_responses=True,
            socket_timeout=5,  # 5 second timeout for operations
            socket_connect_timeout=5  # 5 second timeout for connections
        )
        # Test connection
        redis_client.ping()
        logger.info("Successfully connected to Redis cache")
except (redis.ConnectionError, redis.TimeoutError) as e:
    logger.warning(f"Could not connect to Redis cache: {str(e)}. Caching will be disabled.")
    redis_client = None
except Exception as e:
    logger.warning(f"Unexpected error connecting to Redis: {str(e)}. Caching will be disabled.")
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
                    logger.warning(f"Invalid JSON in cache for query: {query}")
        except (redis.ConnectionError, redis.TimeoutError) as e:
            logger.warning(f"Cache error (non-blocking): {str(e)}")
        except Exception as e:
            logger.warning(f"Unexpected cache error (non-blocking): {str(e)}")

    try:
        # Search for tracklists
        results = search(query)

        # If no results found and query contains "by", try without the "by" clause
        if not results:
            fallback_query = extract_query_without_by(query)
            if fallback_query != query:
                results = search(fallback_query)

        if not results:
            logger.warning(f"No tracks found for query: {query}")
            return {"success": True, "tracks": []}

        # Find the best matching result using fuzzy matching
        logger.info(f"Finding best match from {len(results)} results for query: '{query}'")
        best_match = find_best_match(query, results, min_score=50.0)

        if not best_match:
            logger.warning(f"No suitable match found for query: '{query}' (all results below minimum score threshold)")
            return {"success": True, "results": []}

        logger.info(f"Selected best match: '{best_match['title']}' (score: {best_match.get('match_score', 0):.2f})")

        # Get HTML content from the best matching result only
        html_entries = get_html_from_results([best_match])

        if not html_entries:
            logger.warning(f"No HTML content entries retrieved for query: {query}")
            return {"success": True, "results": []}

        # Parse tracks from each HTML entry
        parsed_results = []
        for entry in html_entries:
            title = entry.get("title", "")
            url = entry.get("url", "")
            html = entry.get("html")
            match_score = best_match.get("match_score")

            if not html:
                # Skip entries without HTML
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
            except Exception as e:
                logger.error(f"Could not extract tracks from '{title}': {str(e)}")
                parsed_results.append({
                    "title": title,
                    "url": url,
                    "tracks": [],
                    "match_score": match_score
                })

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
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Failed to cache result (non-blocking): {str(e)}")
            except Exception as e:
                logger.warning(f"Unexpected error caching result (non-blocking): {str(e)}")

        return result

    except json.JSONDecodeError as e:
        return {"error": f"Failed to parse track data: {str(e)}", "success": False}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}", "success": False}


if __name__ == "__main__":
    asyncio.run(get_tracks())

