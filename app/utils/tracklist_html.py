"""
Pure function to fetch HTML content from MixesDB search results.
"""

from typing import List, Dict, Optional
from .mixesdb import StealthSession


def get_html_from_results(results: List[Dict[str, str]]) -> List[Dict[str, Optional[str]]]:
    """
    Fetch HTML content for each search result.

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
