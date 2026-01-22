"""
Utility functions for working with search queries.
"""

import re


def extract_query_without_by(query: str) -> str:
    """
    Extract the query part before a trailing "by" clause.

    Examples:
        "essential mix by pete tong" -> "essential mix"
        "job jobse" -> "job jobse"

    Args:
        query: The original search query.

    Returns:
        The query without the "by" clause, or the original query if no "by" is found.
    """
    # Look for "by" followed by text (case insensitive)
    pattern = r"\s+by\s+.*$"
    match = re.search(pattern, query, re.IGNORECASE)

    if match:
        # Remove everything from "by" onwards
        cleaned_query = query[: match.start()].strip()
        return cleaned_query

    return query

