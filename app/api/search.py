from fastapi import APIRouter, HTTPException, Request
from app.utils.tracklist_service import get_tracks
from app.utils.youtube_client import youtube_api
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import traceback
import time
import json
import asyncio

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

    # Check if the query parameter is provided
    if not path:
        raise HTTPException(status_code=400, detail="Query parameter required")

    # Convert hyphenated path to space-separated query
    query = path.replace("-", " ")

    print("Search started...")

    try:
        scraper_response = await get_tracks(query)

        # If there's an error with the scraping process
        if not scraper_response.get('success'):
            error_message = scraper_response.get('error', 'Unknown error occurred')
            raise HTTPException(status_code=500, detail=error_message)

        # Process results - each result has title, url, and tracks
        try:
            parsed_results = scraper_response.get('results', [])

            # Process each result: add YouTube links to tracks
            final_results = []
            total_tracks = 0

            for result in parsed_results:
                title = result.get('title', '')
                url = result.get('url', '')
                tracks = result.get('tracks', [])

                if tracks and isinstance(tracks, list):
                    tracks_with_links = await youtube_api.search_tracks_batch(tracks)
                    total_tracks += len(tracks_with_links)
                    final_results.append({
                        "title": title,
                        "url": url,
                        "tracks": tracks_with_links
                    })
                else:
                    final_results.append({
                        "title": title,
                        "url": url,
                        "tracks": []
                    })

            return {
                "query": query,
                "results": final_results,
            }
        except Exception as e:
            return {
                "query": query,
                "results": [],
            }

    # Catch all other exceptions
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
