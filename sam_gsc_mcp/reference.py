"""Static reference data: dimensions, metrics, filter operators, search types."""

from __future__ import annotations

DIMENSIONS = [
    {"api_name": "query", "description": "The search query the user typed into Google. Not available for Discover or Google News."},
    {"api_name": "page", "description": "The canonical URL that received the impression or click."},
    {"api_name": "country", "description": "Searcher's country as a lowercase ISO 3166-1 alpha-3 code, e.g. 'ind', 'usa', 'gbr'."},
    {"api_name": "device", "description": "DESKTOP, MOBILE or TABLET."},
    {"api_name": "date", "description": "Day of the search in YYYY-MM-DD (Pacific Time)."},
    {"api_name": "searchAppearance", "description": "Rich-result or SERP feature type (e.g. AMP_BLUE_LINK, RICHCARD, VIDEO, FAQ_RICH_RESULT). Google only lets you group by it on its own or with date — see the search-appearance-audit skill."},
    {"api_name": "hour", "description": "Hourly breakdown for roughly the last 10 days. Sent to Google as HOUR with dataState HOURLY_ALL; hourly numbers can be partial. Use get_hourly_performance for the easy path."},
]

METRICS = [
    {"api_name": "clicks", "description": "Clicks from Google Search results to your property."},
    {"api_name": "impressions", "description": "Times a URL from your site appeared in results the user could see."},
    {"api_name": "ctr", "description": "Click-through rate. This server returns it as a PERCENTAGE (3.25 means 3.25%)."},
    {"api_name": "position", "description": "Average topmost position of your site. LOWER is better (1 = top)."},
]

OPERATORS = {
    "equals": "Exact match",
    "notEquals": "Does not exactly match",
    "contains": "Contains the substring (case-insensitive in GSC)",
    "notContains": "Does not contain the substring",
    "includingRegex": "Matches the RE2 regular expression",
    "excludingRegex": "Does not match the RE2 regular expression",
}

SEARCH_TYPES = {
    "web": "Regular Google Search (default)",
    "image": "Google Images",
    "video": "Video search",
    "news": "News tab in Google Search",
    "discover": "Google Discover (no query/position data)",
    "googleNews": "news.google.com and the Google News app (no query/position data)",
}

DEVICE_VALUES = ["DESKTOP", "MOBILE", "TABLET"]

COMMON_SEARCH_APPEARANCES = [
    "AMP_BLUE_LINK",
    "AMP_TOP_STORIES",
    "RICHCARD",
    "VIDEO",
    "FAQ_RICH_RESULT",
    "REVIEW_SNIPPET",
    "PRODUCT_SNIPPETS",
    "MERCHANT_LISTINGS",
    "TRANSLATED_RESULT",
    "WEB_LIGHT_RESULT",
]

DATA_STATES = {
    "all": "Includes fresh, not-yet-final data. Matches the Search Console dashboard (default).",
    "final": "Only finalised data. Lags 2-3 days behind the dashboard.",
    "hourly_all": "Used automatically with the hour dimension; may be partial.",
}

FILTER_EXAMPLES = [
    {"dimension": "country", "operator": "equals", "expression": "ind"},
    {"dimension": "device", "operator": "equals", "expression": "MOBILE"},
    {"dimension": "query", "operator": "contains", "expression": "gst registration"},
    {"dimension": "page", "operator": "contains", "expression": "/blog/"},
    {"dimension": "query", "operator": "includingRegex", "expression": "(?i)^(how|what|why)\\b"},
    {"dimension": "query", "operator": "excludingRegex", "expression": "(?i)(brandname|brand name)"},
]

# Rough organic CTR by position (percent). Used only to *estimate* upside in the
# insight tools; real CTR varies a lot by query type and SERP features.
CTR_CURVE = {1: 28.0, 2: 15.0, 3: 11.0, 4: 8.0, 5: 7.0, 6: 5.0, 7: 4.0, 8: 3.0, 9: 2.5, 10: 2.0}


def expected_ctr(position: float) -> float:
    if position <= 1:
        return CTR_CURVE[1]
    if position >= 10:
        return max(0.5, CTR_CURVE[10] - (position - 10) * 0.15)
    lo = int(position)
    hi = lo + 1
    frac = position - lo
    return CTR_CURVE[lo] + (CTR_CURVE[hi] - CTR_CURVE[lo]) * frac
