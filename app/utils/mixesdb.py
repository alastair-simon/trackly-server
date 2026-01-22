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
                    if attempt < max_retries - 1:
                        _human_like_delay(*self.retry_delay)
                        self._setup_session()  # Refresh headers and user agent
                        # Try rotating proxy if using proxy list
                        if self.proxy_list:
                            self.proxies = _get_proxies(self.proxy_list)
                    else:
                        raise
                else:
                    raise
            except requests.exceptions.ProxyError as e:
                error_str = str(e)
                # 407 Unauthorized means authentication failed - don't retry, just fail fast
                if '407' in error_str or 'Unauthorized' in error_str:
                    raise  # Don't retry authentication failures

                if attempt < max_retries - 1:
                    _human_like_delay(*self.retry_delay)
                    # Try rotating proxy if using proxy list
                    if self.proxy_list:
                        self.proxies = _get_proxies(self.proxy_list)
                    self._setup_session()
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
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


def _decompress_response(response):
    """Handle response decompression for various compression types."""
    content_encoding = response.headers.get('Content-Encoding', '').lower()

    if content_encoding in ['gzip', 'deflate']:
        # requests handles these automatically
        if response.encoding is None:
            response.encoding = response.apparent_encoding or 'utf-8'
        return response.text
    elif content_encoding == 'zstd':
        # Server sent zstd - need to decompress manually
        html_content = None

        # Try multiple methods to decompress zstd
        # Method 1: Try zstd library
        try:
            import zstd
            html_content = zstd.decompress(response.content).decode('utf-8')
            return html_content
        except ImportError:
            # Method 2: Try zstandard library
            try:
                import zstandard as zstd_alt
                dctx = zstd_alt.ZstdDecompressor()
                html_content = dctx.decompress(response.content).decode('utf-8')
                return html_content
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
                    return html_content
                except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                    # Last resort: try response.text (will likely fail and return binary)
                    if response.encoding is None:
                        response.encoding = response.apparent_encoding or 'utf-8'
                    return response.text
        except Exception:
            # Last resort: try response.text (will likely fail and return binary)
            if response.encoding is None:
                response.encoding = response.apparent_encoding or 'utf-8'
            return response.text
    else:
        # No compression or unknown - use response.text
        if response.encoding is None:
            response.encoding = response.apparent_encoding or 'utf-8'
        return response.text


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
        # Get the main page
        response = session.get(base_url)
        html_content = _decompress_response(response)
        soup = BeautifulSoup(html_content, 'html.parser')

        # Look for search form
        search_form = None
        search_input = None

        search_selectors = [
            'input[type="search"]',
            'input[name="search"]',
            'input[id="search"]',
            'input[class*="search"]',
            'input[name="q"]',
            'input[name="query"]'
        ]

        for selector in search_selectors:
            elements = soup.select(selector)
            if elements:
                search_input = elements[0]
                search_form = search_input.find_parent('form')
                if search_form:
                    break

        if not search_form or not search_input:
            # Try direct search URL construction
            search_url = f"{base_url}/w/index.php?title=Special:Search&search={quote(query)}"
            response = session.get(search_url)
            html_content = _decompress_response(response)
        else:
            # Extract form data
            form_action = search_form.get('action', '')
            form_method = search_form.get('method', 'get').lower()

            form_data = {}
            for input_elem in search_form.find_all('input'):
                name = input_elem.get('name')
                if name:
                    if input_elem.get('type') in ['search', 'text'] or name in ['search', 'q', 'query']:
                        form_data[name] = query
                    else:
                        form_data[name] = input_elem.get('value', '')

            # If form action is empty or invalid, use MediaWiki search format
            if not form_action or form_action == '/':
                search_url = f"{base_url}/w/index.php?title=Special:Search&search={quote(query)}"
                response = session.get(search_url)
                html_content = _decompress_response(response)
            else:
                search_url = urljoin(base_url, form_action) if form_action else base_url

                if form_method == 'post':
                    response = session.post(search_url, data=form_data)
                else:
                    response = session.get(search_url, params=form_data)
                html_content = _decompress_response(response)

        # Parse search results
        soup = BeautifulSoup(html_content, 'html.parser')

        # Look for result links
        result_selectors = [
            '#catMixesList a',
            '.linkPreviewWrapperList a',
            '.mw-search-results a',
            'a[href*="mix"]',
            'a[href*="tracklist"]'
        ]

        seen_urls = set()
        for selector in result_selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get('href')
                if href and href != '#':
                    full_url = urljoin(base_url, href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        link_text = link.get_text(strip=True)
                        results.append({
                            'title': link_text,
                            'url': full_url
                        })

        return results

    except Exception:
        return []
