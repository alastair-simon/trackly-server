"""
MixesDB result matcher - finds the best matching result from MixesDB search results.

This module uses fuzzy string matching to match a query against an array of MixesDB
results and return the best match.
"""

import re
from typing import List, Dict, Optional
from rapidfuzz import fuzz, process


def normalize_text(text: str) -> str:
    """
    Normalize text for better matching by:
    - Converting to lowercase
    - Removing extra whitespace
    - Removing common punctuation
    - Normalizing spacing around hyphens and commas

    Args:
        text: The text to normalize

    Returns:
        Normalized text string
    """
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Normalize spacing around hyphens and commas
    text = re.sub(r'\s*-\s*', ' ', text)  # Replace hyphens with spaces
    text = re.sub(r'\s*,\s*', ' ', text)  # Replace commas with spaces
    text = re.sub(r'\s+', ' ', text)  # Normalize multiple spaces

    # Remove common punctuation but keep alphanumeric and spaces
    text = re.sub(r'[^\w\s]', '', text)

    # Strip leading/trailing whitespace
    text = text.strip()

    return text


def extract_keywords(text: str) -> List[str]:
    """
    Extract meaningful keywords from text, filtering out common stop words.

    Args:
        text: The text to extract keywords from

    Returns:
        List of keywords
    """
    # Common stop words to filter out
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that',
        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
    }

    normalized = normalize_text(text)
    words = normalized.split()

    # Filter out stop words and very short words (1-2 chars)
    keywords = [w for w in words if len(w) > 2 and w not in stop_words]

    return keywords


def calculate_match_score(query: str, title: str) -> float:
    """
    Calculate a comprehensive match score between query and title using multiple strategies.

    Args:
        query: The search query
        title: The MixesDB result title

    Returns:
        Match score between 0 and 100 (higher is better)
    """
    if not query or not title:
        return 0.0

    # Normalize both strings
    query_norm = normalize_text(query)
    title_norm = normalize_text(title)

    if not query_norm or not title_norm:
        return 0.0

    # Extract keywords for both query and title
    query_keywords = extract_keywords(query)

    # Strategy 1: Keyword matching (check if all query keywords appear in title)
    # This is critical - prioritize results that contain all query terms
    if query_keywords:
        matched_keywords = sum(1 for kw in query_keywords if kw in title_norm)
        keyword_coverage = matched_keywords / len(query_keywords)
        keyword_score = keyword_coverage * 100

        # Apply a penalty if not all keywords are present
        # This ensures results with all keywords rank higher
        keyword_bonus = 20.0 if keyword_coverage == 1.0 else 0.0
        keyword_penalty = (1.0 - keyword_coverage) * 30.0
    else:
        keyword_score = 0.0
        keyword_bonus = 0.0
        keyword_penalty = 0.0

    # Strategy 2: Token Sort Ratio (handles word order differences)
    token_sort_ratio = fuzz.token_sort_ratio(query_norm, title_norm)

    # Strategy 3: Token Set Ratio (handles duplicates and subsets)
    token_set_ratio = fuzz.token_set_ratio(query_norm, title_norm)

    # Strategy 4: Partial Ratio (checks if query is substring of title)
    partial_ratio = fuzz.partial_ratio(query_norm, title_norm)

    # Strategy 5: Simple Ratio (exact match)
    simple_ratio = fuzz.ratio(query_norm, title_norm)

    # Weighted combination of scores
    # Keyword coverage is most important - we want results with all query terms
    # Token-based scores handle word order variations
    # Partial ratio helps catch cases where query is part of title
    base_score = (
        token_sort_ratio * 0.25 +
        token_set_ratio * 0.25 +
        partial_ratio * 0.20 +
        simple_ratio * 0.10 +
        keyword_score * 0.20
    )

    # Apply bonuses and penalties
    final_score = base_score + keyword_bonus - keyword_penalty

    # Ensure score is within valid range
    final_score = max(0.0, min(100.0, final_score))

    return final_score


def find_best_match(query: str, results: List[Dict[str, str]], min_score: float = 50.0) -> Optional[Dict[str, str]]:
    """
    Find the best matching result from MixesDB search results.

    Args:
        query: The search query string
        results: List of dictionaries with 'title' and 'url' keys from MixesDB search
        min_score: Minimum match score threshold (0-100). Results below this will return None.
                   Default is 50.0 to ensure reasonable matches.

    Returns:
        The best matching result dictionary with 'title' and 'url' keys, or None if no match
        meets the minimum score threshold. The result will also include a 'match_score' key.

    Example:
        >>> query = 'leon vynehall francis inferno'
        >>> results = [
        ...     {'title': '2014-05-23 -LeonVynehall, Francis Inferno Orchestra - Solid Steel', 'url': '...'},
        ...     {'title': 'Some Other Mix', 'url': '...'}
        ... ]
        >>> best = find_best_match(query, results)
        >>> best['title']
        '2014-05-23 -LeonVynehall, Francis Inferno Orchestra - Solid Steel'
    """
    if not results:
        return None

    if not query or not query.strip():
        return None

    # Calculate scores for all results
    scored_results = []
    for result in results:
        title = result.get('title', '')
        if not title:
            continue

        score = calculate_match_score(query, title)
        scored_results.append({
            **result,
            'match_score': score
        })

    if not scored_results:
        return None

    # Sort by score (descending) and get the best match
    scored_results.sort(key=lambda x: x['match_score'], reverse=True)
    best_match = scored_results[0]

    # Check if score meets minimum threshold
    if best_match['match_score'] < min_score:
        return None

    return best_match


def find_best_matches(query: str, results: List[Dict[str, str]], top_n: int = 5, min_score: float = 30.0) -> List[Dict[str, str]]:
    """
    Find the top N best matching results from MixesDB search results.

    Args:
        query: The search query string
        results: List of dictionaries with 'title' and 'url' keys from MixesDB search
        top_n: Number of top results to return (default: 5)
        min_score: Minimum match score threshold (0-100). Results below this will be excluded.
                   Default is 30.0 to include more potential matches.

    Returns:
        List of top N matching results, each with 'title', 'url', and 'match_score' keys.
        Results are sorted by score (descending).
    """
    if not results:
        return []

    if not query or not query.strip():
        return []

    # Calculate scores for all results
    scored_results = []
    for result in results:
        title = result.get('title', '')
        if not title:
            continue

        score = calculate_match_score(query, title)
        if score >= min_score:
            scored_results.append({
                **result,
                'match_score': score
            })

    # Sort by score (descending) and return top N
    scored_results.sort(key=lambda x: x['match_score'], reverse=True)

    return scored_results[:top_n]
