"""
Pure function to fetch HTML content from MixesDB search results.
"""

import logging
from typing import List, Dict, Optional
from .mixesdb import StealthSession

logger = logging.getLogger(__name__)


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

    logger.info(f"Fetching HTML for {len(results)} results")
    session = StealthSession()
    html_results: List[Dict[str, Optional[str]]] = []

    for idx, result in enumerate(results, 1):
        title = result.get("title") or ""
        url = result.get("url")

        if not url:
            logger.warning(f"Result {idx}/{len(results)} ({title}) has no URL")
            html_results.append(
                {
                    "title": title,
                    "url": "",
                    "html": None,
                }
            )
            continue

        try:
            logger.info(f"Fetching HTML {idx}/{len(results)}: {title} - {url}")
            response = session.get(url)
            html_results.append(
                {
                    "title": title,
                    "url": url,
                    "html": response.text,
                }
            )
            logger.info(f"Successfully fetched HTML {idx}/{len(results)}: {len(response.text)} chars")
        except Exception as e:
            logger.error(f"Failed to fetch HTML {idx}/{len(results)} ({title}): {str(e)}")
            html_results.append(
                {
                    "title": title,
                    "url": url,
                    "html": None,
                }
            )

    logger.info(f"Completed fetching HTML: {len([r for r in html_results if r.get('html')])} successful out of {len(html_results)}")
    return html_results
