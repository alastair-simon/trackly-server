import os
import aiohttp
from typing import Optional, Dict, Any, Tuple
import asyncio
import json
import hashlib
import redis

class YouTubeAPI:
    def __init__(self):
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.session = None  # Reusable session for connection pooling
        self.semaphore = asyncio.Semaphore(10)  # Limit concurrent requests to 10

        # Initialize Redis client for caching YouTube results
        self.redis_client = None
        try:
            redis_url = os.getenv('REDIS_URL')
            if redis_url:
                self.redis_client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
            else:
                redis_host = os.getenv('REDIS_HOST')
                redis_port = os.getenv('REDIS_PORT', '6379')
                if redis_host:
                    self.redis_client = redis.Redis(
                        host=redis_host,
                        port=int(redis_port),
                        decode_responses=True,
                        socket_timeout=5,
                        socket_connect_timeout=5
                    )
            if self.redis_client:
                self.redis_client.ping()
        except Exception:
            self.redis_client = None

        # YouTube cache TTL (7 days - YouTube results don't change often)
        self.cache_ttl = 7 * 24 * 60 * 60

    def _get_cache_key(self, artist: str, track: str) -> str:
        """Generate a cache key for a track search."""
        # Normalize and create hash for consistent caching
        normalized = f"{artist.lower().strip()}|{track.lower().strip()}"
        cache_key = hashlib.md5(normalized.encode()).hexdigest()
        return f"youtube:{cache_key}"

    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create a reusable HTTP session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def search_track(self, artist: str, track: str, use_cache: bool = True) -> Optional[Dict[str, str]]:
        """
        Search for a track on YouTube and return the first video URL and thumbnail.
        Uses caching and connection pooling for better performance.

        Args:
            artist: Artist name
            track: Track name
            use_cache: Whether to use cached results (default: True)

        Returns:
            Dictionary with 'link' and 'thumbnail' keys if found, None otherwise
        """
        if not self.api_key:
            return None

        # Check cache first
        if use_cache and self.redis_client:
            try:
                cache_key = self._get_cache_key(artist, track)
                cached_result = self.redis_client.get(cache_key)
                if cached_result:
                    try:
                        result = json.loads(cached_result)
                        # Return None if cached as "not found"
                        if result == {}:
                            return None
                        return result
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        # Combine artist and track for search query
        search_query = f"{artist} {track}"

        # Use semaphore to limit concurrent requests
        async with self.semaphore:
            try:
                session = self._get_session()
                params = {
                    'part': 'snippet',
                    'q': search_query,
                    'key': self.api_key,
                    'type': 'video',
                    'maxResults': 1,
                    'videoEmbeddable': 'true'
                }

                url = f"{self.base_url}/search"
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        data = await response.json()

                        if data.get('items'):
                            video_id = data['items'][0]['id']['videoId']
                            snippet = data['items'][0]['snippet']

                            # Extract thumbnail URL (get any available quality)
                            thumbnails = snippet.get('thumbnails', {})
                            thumbnail_url = ""

                            # Get the first available thumbnail
                            if thumbnails:
                                # Get any available thumbnail quality
                                first_thumbnail = next(iter(thumbnails.values()))
                                thumbnail_url = first_thumbnail['url']

                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                            result = {'link': video_url, 'thumbnail': thumbnail_url}

                            # Cache the result
                            if use_cache and self.redis_client:
                                try:
                                    cache_key = self._get_cache_key(artist, track)
                                    self.redis_client.setex(
                                        cache_key,
                                        self.cache_ttl,
                                        json.dumps(result)
                                    )
                                except Exception:
                                    pass

                            return result
                        else:
                            # Cache "not found" result to avoid repeated failed searches
                            if use_cache and self.redis_client:
                                try:
                                    cache_key = self._get_cache_key(artist, track)
                                    self.redis_client.setex(
                                        cache_key,
                                        self.cache_ttl,
                                        json.dumps({})  # Empty dict means not found
                                    )
                                except Exception:
                                    pass
                            return None
                    else:
                        return None

            except Exception:
                return None

    async def _process_single_track(self, track: dict) -> dict:
        """Process a single track and add YouTube links."""
        if 'artist' in track and 'track' in track:
            youtube_result = await self.search_track(track['artist'], track['track'])
            if youtube_result:
                track['link'] = youtube_result['link']
                track['thumbnail'] = youtube_result['thumbnail']
            else:
                track['link'] = ""
                track['thumbnail'] = ""
        else:
            track['link'] = ""
            track['thumbnail'] = ""
        return track

    async def search_tracks_batch(self, tracks: list) -> list:
        """
        Search for multiple tracks on YouTube and add links and thumbnails to the track objects.
        Processes tracks in parallel for better performance.

        Args:
            tracks: List of track dictionaries with 'artist' and 'track' keys

        Returns:
            List of track dictionaries with added 'link' and 'thumbnail' keys
        """
        if not self.api_key:
            # Add empty link and thumbnail fields to all tracks when API key is not configured
            for track in tracks:
                track['link'] = ""
                track['thumbnail'] = ""
            return tracks

        # Process all tracks in parallel using asyncio.gather
        # The semaphore in search_track will limit concurrent API calls
        tasks = [self._process_single_track(track.copy()) for track in tracks]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions that occurred
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                # If an exception occurred, add empty fields
                track = tracks[i].copy()
                track['link'] = ""
                track['thumbnail'] = ""
                processed_results.append(track)
            else:
                processed_results.append(result)

        return processed_results

    async def close(self):
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

# Global instance
youtube_api = YouTubeAPI()