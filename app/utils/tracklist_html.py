"""
Pure function to fetch HTML content from MixesDB search results.
"""

from typing import List, Dict, Optional
import asyncio
from .mixesdb import StealthSession, AsyncStealthSession, _async_decompress_response


def get_html_from_results(results: List[Dict[str, str]]) -> List[Dict[str, Optional[str]]]:
    """
    Fetch HTML content for each search result (synchronous version for backward compatibility).

    Args:
        results: List of dictionaries with 'title' and 'url' keys from mixesdb.search()

    Returns:
        List of dictionaries, one per result:
        {
            "title": <result title>,
            "url": <result url>,
            "html": <HTML string or None if fetch failed>
        }
    """
    if not results:
        return []

    session = StealthSession()
    html_results: List[Dict[str, Optional[str]]] = []

    for idx, result in enumerate(results, 1):
        title = result.get("title") or ""
        url = result.get("url")

        if not url:
            html_results.append(
                {
                    "title": title,
                    "url": "",
                    "html": None,
                }
            )
            continue

        try:
            response = session.get(url)

            # Handle compression - requests auto-decompresses gzip/deflate
            # We removed zstd from Accept-Encoding header, so server should send gzip/deflate
            content_encoding = response.headers.get('Content-Encoding', '').lower()

            if content_encoding in ['gzip', 'deflate']:
                # requests handles these automatically
                if response.encoding is None:
                    response.encoding = response.apparent_encoding or 'utf-8'
                html_content = response.text
            elif content_encoding == 'zstd':
                # Server sent zstd - need to decompress manually
                html_content = None

                # Try multiple methods to decompress zstd
                # Method 1: Try zstd library
                try:
                    import zstd
                    html_content = zstd.decompress(response.content).decode('utf-8')
                except ImportError:
                    # Method 2: Try zstandard library
                    try:
                        import zstandard as zstd_alt
                        dctx = zstd_alt.ZstdDecompressor()
                        html_content = dctx.decompress(response.content).decode('utf-8')
                    except ImportError:
                        # Method 3: Try system zstd command (if available)
                        import subprocess
                        try:
                            result = subprocess.run(
                                ['zstd', '-d', '--stdout'],
                                input=response.content,
                                capture_output=True,
                                check=True,
                                timeout=10
                            )
                            html_content = result.stdout.decode('utf-8')
                        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                            if response.encoding is None:
                                response.encoding = response.apparent_encoding or 'utf-8'
                            html_content = response.text
                except Exception:
                    if response.encoding is None:
                        response.encoding = response.apparent_encoding or 'utf-8'
                    html_content = response.text

                if html_content is None:
                    html_content = response.content.decode('utf-8', errors='ignore')
            else:
                # No compression or unknown - use response.text
                if response.encoding is None:
                    response.encoding = response.apparent_encoding or 'utf-8'
                html_content = response.text

            # Verify it's actually text (not binary)
            if html_content and not isinstance(html_content, str):
                try:
                    html_content = html_content.decode('utf-8')
                except (UnicodeDecodeError, AttributeError):
                    html_content = response.content.decode('utf-8', errors='ignore')
            html_results.append(
                {
                    "title": title,
                    "url": url,
                    "html": html_content,
                }
            )
        except Exception:
            html_results.append(
                {
                    "title": title,
                    "url": url,
                    "html": None,
                }
            )

    return html_results


async def get_html_from_results_async(results: List[Dict[str, str]]) -> List[Dict[str, Optional[str]]]:
    """
    Fetch HTML content for each search result in parallel (async version for better performance).

    Args:
        results: List of dictionaries with 'title' and 'url' keys from mixesdb.search_async()

    Returns:
        List of dictionaries, one per result:
        {
            "title": <result title>,
            "url": <result url>,
            "html": <HTML string or None if fetch failed>
        }
    """
    if not results:
        return []

    session = AsyncStealthSession()

    async def fetch_single_result(result: Dict[str, str]) -> Dict[str, Optional[str]]:
        """Fetch HTML for a single result."""
        title = result.get("title") or ""
        url = result.get("url")

        if not url:
            return {
                "title": title,
                "url": "",
                "html": None,
            }

        try:
            response = await session.get(url, skip_delay=True)  # Skip delay for parallel requests
            html_content = await _async_decompress_response(response)

            # Verify it's actually text (not binary)
            if html_content and not isinstance(html_content, str):
                try:
                    html_content = html_content.decode('utf-8')
                except (UnicodeDecodeError, AttributeError):
                    html_content = str(html_content)

            return {
                "title": title,
                "url": url,
                "html": html_content,
            }
        except Exception:
            return {
                "title": title,
                "url": url,
                "html": None,
            }

    # Fetch all results in parallel
    tasks = [fetch_single_result(result) for result in results]
    html_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions
    processed_results = []
    for i, result in enumerate(html_results):
        if isinstance(result, Exception):
            processed_results.append({
                "title": results[i].get("title") or "",
                "url": results[i].get("url") or "",
                "html": None,
            })
        else:
            processed_results.append(result)

    await session.close()
    return processed_results
