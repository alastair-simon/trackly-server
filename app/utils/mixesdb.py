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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
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
            'Accept-Encoding': 'gzip, deflate, br, zstd',
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

        # Parse search results
        soup = BeautifulSoup(response.content, 'html.parser')

        # Debug: Log page structure to help diagnose parsing issues
        logger.debug(f"Page title: {soup.title.string if soup.title else 'No title'}")
        category_sections = soup.select('#mw-pages, #mw-subcategories, .mw-category-group')
        logger.debug(f"Found {len(category_sections)} MediaWiki category sections")

        # Look for result links - MediaWiki category pages have specific structure
        result_selectors = [
            '#mw-pages a',  # MediaWiki category page links
            '#mw-subcategories a',  # MediaWiki subcategory links
            '.mw-category-group a',  # MediaWiki category group links
            '.mw-category a',  # MediaWiki category links
            '#catMixesList a',  # MixesDB specific
            '.linkPreviewWrapperList a',  # MixesDB specific
            '.mw-search-results a',  # MediaWiki search results
            'a[href*="/w/"]',  # Any MediaWiki page link
            'a[href*="mix"]',  # Links containing "mix"
            'a[href*="tracklist"]'  # Links containing "tracklist"
        ]

        seen_urls = set()
        for selector in result_selectors:
            links = soup.select(selector)
            if links:
                logger.debug(f"Found {len(links)} links using selector: {selector}")
            for link in links:
                href = link.get('href')
                if href and href != '#' and not href.startswith('#'):
                    # Skip category links and other non-tracklist links
                    if '/Category:' in href or '/Special:' in href or '/File:' in href:
                        continue
                    full_url = urljoin(base_url, href)
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        link_text = link.get_text(strip=True)
                        if link_text:  # Only add if link has text
                            results.append({
                                'title': link_text,
                                'url': full_url
                            })
        # Log all results for debugging/inspection
        logger.info("MixesDB search for '%s' returned %d results:", query, len(results))
        for idx, item in enumerate(results, start=1):
            logger.info("  #%d: %s -> %s", idx, item.get("title", ""), item.get("url", ""))

        return results

    except Exception as e:
        logger.error("MixesDB search for '%s' failed: %s", query, str(e))
        return []
