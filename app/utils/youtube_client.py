import os
import aiohttp
from typing import Optional, Dict, Any, Tuple
import asyncio

class YouTubeAPI:
    def __init__(self):
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        self.base_url = "https://www.googleapis.com/youtube/v3"

    async def search_track(self, artist: str, track: str) -> Optional[Dict[str, str]]:
        """
        Search for a track on YouTube and return the first video URL and thumbnail.

        Args:
            artist: Artist name
            track: Track name

        Returns:
            Dictionary with 'link' and 'thumbnail' keys if found, None otherwise
        """
        if not self.api_key:
            return None

        # Combine artist and track for search query
        search_query = f"{artist} {track}"

        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    'part': 'snippet',
                    'q': search_query,
                    'key': self.api_key,
                    'type': 'video',
                    'maxResults': 1,
                    'videoEmbeddable': 'true'
                }

                url = f"{self.base_url}/search"
                async with session.get(url, params=params) as response:
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
                            return {'link': video_url, 'thumbnail': thumbnail_url}
                        else:
                            return None
                    else:
                        return None

        except Exception:
            return None

    async def search_tracks_batch(self, tracks: list) -> list:
        """
        Search for multiple tracks on YouTube and add links and thumbnails to the track objects.

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

        # Process tracks with a small delay to respect API rate limits
        results = []
        for track in tracks:
            if 'artist' in track and 'track' in track:
                # Add a small delay between requests to avoid rate limiting
                await asyncio.sleep(0.1)

                youtube_result = await self.search_track(track['artist'], track['track'])
                if youtube_result:
                    track['link'] = youtube_result['link']
                    track['thumbnail'] = youtube_result['thumbnail']
                else:
                    track['link'] = ""
                    track['thumbnail'] = ""

            results.append(track)

        return results

# Global instance
youtube_api = YouTubeAPI()