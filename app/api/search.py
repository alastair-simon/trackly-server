from fastapi import APIRouter, HTTPException, Request
from app.utils.tracklist_service import get_tracks
from app.utils.youtube_client import youtube_api
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import traceback
import time
import logging
import json
import asyncio

# Configure logging with custom formatter
class CustomFormatter(logging.Formatter):
    """Custom formatter with visual separators and better formatting"""

    # Colors for different log levels
    grey = "\x1b[38;21m"
    blue = "\x1b[34;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"

    # Format strings
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: blue + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler with custom formatter
console_handler = logging.StreamHandler()
console_handler.setFormatter(CustomFormatter())
logger.addHandler(console_handler)

# Prevent duplicate logs
logger.propagate = False

def log_section(title: str, level: str = "info"):
    """Log a section header with visual separators"""
    separator = "=" * 60
    message = f"\n{separator}\n{title.center(60)}\n{separator}"
    if level == "info":
        logger.info(message)
    elif level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)

def log_subsection(title: str, level: str = "info"):
    """Log a subsection header with visual separators"""
    separator = "-" * 40
    message = f"\n{separator}\n{title.center(40)}\n{separator}"
    if level == "info":
        logger.info(message)
    elif level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)

router = APIRouter()

class SearchRequest(BaseModel):
    query: str

class SearchResponse(BaseModel):
    query: str
    results: List[Dict[str, Any]]  # One entry per MixesDB result with title, url, and tracks

class UrlRequest(BaseModel):
    url: HttpUrl

class UrlResponse(BaseModel):
    url: str
    status: str
    details: Dict[str, Any]

@router.get("/warmup")
async def warmup(request: Request):
    return {"status": "ready"}

@router.get("/search/{path:path}", response_model=SearchResponse)
async def search_by_path(path: str, request: Request):
    start_time = time.time()

    # Log search start with visual separator
    log_section("SEARCH REQUEST STARTED")
    logger.info(f"Search Query: '{path}'")
    logger.info(f"Start Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check if the query parameter is provided
    if not path:
        log_subsection("VALIDATION ERROR", "error")
        logger.error("Query parameter required")
        raise HTTPException(status_code=400, detail="Query parameter required")

    # Convert hyphenated path to space-separated query
    query = path.replace("-", " ")
    logger.info(f"Processed Query: '{query}'")

    try:
        # Start scraping
        log_subsection("TRACK SCRAPING")
        logger.info(f"Starting track scraping for: '{query}'")
        scraper_response = await get_tracks(query)

        # If there's an error with the scraping process
        if not scraper_response.get('success'):
            log_subsection("SCRAPING ERROR", "error")
            error_message = scraper_response.get('error', 'Unknown error occurred')
            logger.error(f"Scraper failed for query '{query}': {error_message}")
            raise HTTPException(status_code=500, detail=error_message)

        logger.info("Track scraping completed successfully")

        # Process results - each result has title, url, and tracks
        log_subsection("DATA PROCESSING")
        try:
            parsed_results = scraper_response.get('results', [])
            logger.info(f"Found {len(parsed_results)} MixesDB results")

            # Process each result: add YouTube links to tracks
            log_subsection("YOUTUBE SEARCH")
            final_results = []
            total_tracks = 0

            for result in parsed_results:
                title = result.get('title', '')
                url = result.get('url', '')
                tracks = result.get('tracks', [])
                html = result.get('html')  # Get HTML from result

                if tracks and isinstance(tracks, list):
                    logger.info(f"Processing '{title}': {len(tracks)} tracks")
                    tracks_with_links = await youtube_api.search_tracks_batch(tracks)
                    total_tracks += len(tracks_with_links)
                    final_results.append({
                        "title": title,
                        "url": url,
                        "tracks": tracks_with_links,
                        "html": html  # Include HTML in response
                    })
                else:
                    final_results.append({
                        "title": title,
                        "url": url,
                        "tracks": [],
                        "html": html  # Include HTML in response
                    })

            logger.info(f"YouTube search completed: {total_tracks} total tracks across {len(final_results)} results")

            elapsed_time = time.time() - start_time
            log_subsection("SEARCH COMPLETED")
            logger.info(f"Total execution time: {elapsed_time:.2f} seconds")
            logger.info(f"Results count: {len(final_results)} sources, {total_tracks} total tracks")

            return {
                "query": query,
                "results": final_results,
            }
        except Exception as e:
            log_subsection("PROCESSING ERROR", "error")
            error_msg = f"Failed to process results for '{query}': {str(e)}"
            logger.error(f"{error_msg}")
            elapsed_time = time.time() - start_time
            logger.info(f"Search completed in {elapsed_time:.2f} seconds (with processing error)")
            return {
                "query": query,
                "results": [],
            }

    # Catch all other exceptions
    except HTTPException:
        raise
    except Exception as e:
        log_subsection("UNEXPECTED ERROR", "error")
        error_detail = f"Error processing search: {str(e)}\nTraceback: {traceback.format_exc()}"
        logger.error(f"{error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)
