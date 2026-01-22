"""
MixesDB search client - searches MixesDB and returns tracklist results.
"""

import requests
from bs4 import BeautifulSoup
import random
import time
import os
from urllib.parse import urljoin, quote
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


COMMON_USER_AGENTS = [
    # Older browsers that typically don't support zstd - may get gzip instead
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    # Even older browsers
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/109.0",
    # Mobile user agents (often get different compression)
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
]


def _human_like_delay(min_delay=2000, max_delay=5000):
    """Add a random delay to mimic human behavior."""
    delay = random.uniform(min_delay, max_delay) / 1000
    time.sleep(delay)


def _get_proxy_list():
    """Get proxy list from environment variables."""
    proxy_list_env = os.getenv('PROXY_LIST') or os.getenv('proxy_list')
    if proxy_list_env:
        return [p.strip() for p in proxy_list_env.split(',') if p.strip()]
    return None


def _get_proxies(proxy_list=None):
    """Get proxy configuration from environment variables or proxy list."""
    proxies = {}

    # Check for single proxy
    http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')

    if http_proxy:
        proxies['http'] = http_proxy
    if https_proxy:
        proxies['https'] = https_proxy

    # Use proxy list if provided and no single proxy is set
    if proxy_list and not proxies:
        if proxy_list:
            # Use random proxy from list
            selected_proxy = random.choice(proxy_list)

            # Add authentication if credentials are provided
            proxy_username = os.getenv('PROXY_USERNAME') or os.getenv('proxy_username')
            proxy_password = os.getenv('PROXY_PASSWORD') or os.getenv('proxy_password')
            proxy_country = os.getenv('PROXY_COUNTRY', 'US')  # Default to US if not specified

            # Extract customer ID if email format was provided (remove @domain part)
            # Oxylabs customer ID should not include @ symbol
            if proxy_username and '@' in proxy_username:
                proxy_username = proxy_username.split('@')[0]
                logger.warning(f"Extracted customer ID '{proxy_username}' from email address. Use just the customer ID in PROXY_USERNAME.")

            if proxy_username and proxy_password:
                # Oxylabs requires specific format: user-USERNAME-country-COUNTRY:PASSWORD@host:port
                # Format: https://user-USERNAME-country-COUNTRY:PASSWORD@dc.oxylabs.io:PORT
                formatted_username = f"user-{proxy_username}-country-{proxy_country}"
                # URL encode password to handle special characters like ?, @, :, etc.
                # These characters break URL parsing if not encoded
                encoded_password = quote(proxy_password, safe='')

                # Extract host:port from proxy (remove any existing protocol)
                if '://' in selected_proxy:
                    _, proxy_host_port = selected_proxy.split('://', 1)
                else:
                    proxy_host_port = selected_proxy

                # Use https:// protocol as shown in Oxylabs example
                authenticated_proxy = f"https://{formatted_username}:{encoded_password}@{proxy_host_port}"
                selected_proxy = authenticated_proxy
                # Log without showing credentials
                logger.info(f"Using authenticated Oxylabs proxy: {proxy_host_port}")
            else:
                logger.info(f"Using proxy from list: {selected_proxy}")

            # Oxylabs example shows only setting 'https' in proxies dict
            # Use https for both http and https requests
            proxies = {
                'http': selected_proxy,
                'https': selected_proxy
            }

    return proxies if proxies else None


class StealthSession:
    """HTTP session with stealth features to avoid being blocked."""

    def __init__(self, min_delay=2000, max_delay=5000, retry_delay=(10000, 15000)):
        self.session = requests.Session()
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.retry_delay = retry_delay
        self.proxy_list = _get_proxy_list()
        self.proxies = _get_proxies(self.proxy_list)
        if self.proxies:
            logger.info(f"Proxy configuration enabled: {self.proxies}")
        self._setup_session()

    def _setup_session(self):
        """Configure session with stealth headers."""
        user_agent = random.choice(COMMON_USER_AGENTS)
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            # Only request gzip/deflate (not zstd/br) since requests auto-decompresses these
            # zstd requires additional library that has build issues on Python 3.13
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://www.google.com/'
        })

    def _make_request(self, method, url, **kwargs):
        """Common request handling with retries and delays."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                _human_like_delay(self.min_delay, self.max_delay)

                # Add proxies to request if configured
                request_kwargs = kwargs.copy()
                if self.proxies:
                    request_kwargs['proxies'] = self.proxies

                response = getattr(self.session, method)(url, timeout=30, **request_kwargs)
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 403:
                    logger.warning(f"403 Forbidden for {url} - MixesDB may be blocking requests. Attempt {attempt + 1}/{max_retries}")
                    if attempt < max_retries - 1:
                        _human_like_delay(*self.retry_delay)
                        self._setup_session()  # Refresh headers and user agent
                        # Try rotating proxy if using proxy list
                        if self.proxy_list:
                            self.proxies = _get_proxies(self.proxy_list)
                            logger.info(f"Rotating proxy for retry: {self.proxies}")
                    else:
                        raise
                else:
                    raise
            except requests.exceptions.ProxyError as e:
                error_str = str(e)
                # 407 Unauthorized means authentication failed - don't retry, just fail fast
                if '407' in error_str or 'Unauthorized' in error_str:
                    logger.error(f"Proxy authentication failed (407 Unauthorized) for {url}. Check PROXY_USERNAME and PROXY_PASSWORD environment variables.")
                    raise  # Don't retry authentication failures

                logger.warning(f"Proxy error for {url}: {error_str}. Attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    _human_like_delay(*self.retry_delay)
                    # Try rotating proxy if using proxy list
                    if self.proxy_list:
                        self.proxies = _get_proxies(self.proxy_list)
                        logger.info(f"Rotating proxy after error: {self.proxies}")
                    self._setup_session()
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request failed for {url}: {str(e)}. Retrying...")
                    _human_like_delay(*self.retry_delay)
                    # Try rotating proxy if using proxy list
                    if self.proxy_list:
                        self.proxies = _get_proxies(self.proxy_list)
                    self._setup_session()
                else:
                    raise
        return None

    def get(self, url, **kwargs):
        """Enhanced GET request with retries."""
        return self._make_request('get', url, **kwargs)

    def post(self, url, **kwargs):
        """Enhanced POST request with retries."""
        return self._make_request('post', url, **kwargs)


def search(query: str) -> List[Dict[str, str]]:
    """
    Search MixesDB for tracklists matching the query.

    Args:
        query: The search query to look for

    Returns:
        List of dictionaries with 'title' and 'url' keys, empty list if no results found
    """
    base_url = "https://www.mixesdb.com"
    session = StealthSession()
    results = []

    try:
        # MixesDB uses MediaWiki category format
        # Format: /w/Category:Artist_Name (with underscores and proper capitalization)
        # Convert query to category format: replace spaces with underscores, capitalize words
        category_name = query.replace(' ', '_')
        # Capitalize first letter of each word (e.g., "leon vynehall" -> "Leon_Vynehall")
        category_name = '_'.join(word.capitalize() for word in category_name.split('_'))
        search_url = f"{base_url}/w/Category:{category_name}"
        logger.info(f"Searching MixesDB category: {search_url}")
        response = session.get(search_url)

        # If category page doesn't exist (404), try MediaWiki search as fallback
        if response.status_code == 404:
            logger.warning(f"Category page not found, trying MediaWiki search as fallback")
            search_url = f"{base_url}/w/index.php?title=Special:Search&search={quote(query)}"
            logger.info(f"Using MediaWiki search: {search_url}")
            response = session.get(search_url)

        # TEMPORARY: Return the full HTML page content
        # This allows us to see what's on the page without parsing
        logger.info(f"Returning full page HTML (parsing disabled): {search_url}")

        # Handle compression - requests auto-decompresses gzip/deflate
        # We removed zstd from Accept-Encoding header, so server should send gzip/deflate
        content_encoding = response.headers.get('Content-Encoding', '').lower()
        logger.info(f"Response encoding: {response.encoding}, Content-Encoding: {content_encoding}")

        if content_encoding in ['gzip', 'deflate']:
            # requests handles these automatically
            if response.encoding is None:
                response.encoding = response.apparent_encoding or 'utf-8'
            html_content = response.text
        elif content_encoding == 'zstd':
            # Server sent zstd - need to decompress manually
            logger.warning(f"Server sent zstd compression. Attempting to decompress manually.")
            html_content = None

            # Try multiple methods to decompress zstd
            # Method 1: Try zstd library
            try:
                import zstd
                html_content = zstd.decompress(response.content).decode('utf-8')
                logger.info(f"Successfully decompressed zstd content using zstd library")
            except ImportError:
                # Method 2: Try zstandard library
                try:
                    import zstandard as zstd_alt
                    dctx = zstd_alt.ZstdDecompressor()
                    html_content = dctx.decompress(response.content).decode('utf-8')
                    logger.info(f"Successfully decompressed zstd content using zstandard library")
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
                        logger.info(f"Successfully decompressed zstd content using system zstd command")
                    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                        logger.error("Cannot decompress zstd: no zstd library or system command available")
                        # Last resort: try response.text (will likely fail and return binary)
                        if response.encoding is None:
                            response.encoding = response.apparent_encoding or 'utf-8'
                        html_content = response.text
            except Exception as e:
                logger.error(f"Failed to decompress zstd: {e}")
                # Last resort: try response.text (will likely fail and return binary)
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

        logger.info(f"Page HTML length: {len(html_content)} characters")
        # Log first 200 chars to verify it's text
        logger.info(f"HTML preview (first 200 chars): {html_content[:200] if html_content else 'empty'}")
        results.append({
            'title': f"Category: {category_name}",
            'url': search_url,
            'html': html_content
        })

        return results

    except Exception as e:
        logger.error("MixesDB search for '%s' failed: %s", query, str(e))
        return []
