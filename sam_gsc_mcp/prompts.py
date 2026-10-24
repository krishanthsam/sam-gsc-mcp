"""MCP prompts: one-click SEO workflows that clients show in their prompt/slash menus."""

_QUIRKS = (
    "Data quirks: ctr is a percentage; position is an average where lower is better; data lags 1-3 days, "
    "so don't treat the most recent 2 days as final."
)


def _site_line(site_url: str) -> str:
    s = site_url.strip()
    return f"Property: {s}" if s else "Property: call list_properties first and ask which one if there are several."


def _clean(text: str) -> str:
    return "\n".join(line[4:] if line.startswith("    ") else line for line in text.splitlines())


def register(mcp) -> None:
    """Attach all workflow prompts to the server."""

    @mcp.prompt(name="seo-weekly-report", title="SEO weekly report", description="28-day performance snapshot, period-over-period changes, alerts and top queries.")
    def seo_weekly_report(site_url: str = "") -> str:
        return _clean(f"""Create a weekly SEO report from Google Search Console.
    {_site_line(site_url)}

    Steps:
    1. skill_read("seo-weekly-report") and follow it.
    2. get_site_summary(period_days=28) for totals and % change vs the previous 28 days.
    3. compare_search_periods(dimensions="query", limit=20) — flag queries whose clicks fell more than 20%.
    4. get_search_analytics(dimensions="query", row_limit=10) for the top 10 queries, and dimensions="page" for top pages.
    5. find_striking_distance_keywords(limit=10) for next week's quick wins.
    6. Write a short markdown report: snapshot table, alerts, top queries/pages, 3-5 prioritised actions.

    {_QUIRKS}""")


    @mcp.prompt(name="content-opportunities", title="Find content opportunities", description="Striking-distance queries, low-CTR pages and content gaps worth acting on.")
    def content_opportunities(site_url: str = "", focus_area: str = "") -> str:
        focus = f"Focus area: {focus_area.strip()}\n" if focus_area.strip() else ""
        return _clean(f"""Find concrete content opportunities from Google Search Console data.
    {_site_line(site_url)}
    {focus}
    Steps:
    1. skill_read("content-opportunities").
    2. find_striking_distance_keywords — positions 4-20 with real impressions (improve existing pages).
    3. find_low_ctr_opportunities — top-5 positions with weak CTR (rewrite titles/metas, add click reasons).
    4. get_advanced_search_analytics(dimensions="query", filters=[{{"dimension":"query","operator":"includingRegex","expression":"(?i)^(how|what|why|best|vs)\\\\b"}}]) — question queries without a dedicated page are new-content candidates.
    5. Return a prioritised table: opportunity, query, page, metrics, recommended action.

    {_QUIRKS}""")


    @mcp.prompt(name="cannibalization-check", title="Keyword cannibalization check", description="Queries where several of your pages compete, with a fix for each.")
    def cannibalization_check(site_url: str = "") -> str:
        return _clean(f"""Check for keyword cannibalization.
    {_site_line(site_url)}

    Steps:
    1. skill_read("keyword-cannibalization").
    2. find_keyword_cannibalization(limit=20).
    3. For the top 5 conflicts, run get_search_by_page_query on each competing page to see their overall query mix.
    4. Recommend per conflict: keep/merge/redirect/differentiate, which page is primary, and internal-link changes.

    {_QUIRKS}""")


    @mcp.prompt(name="indexing-audit", title="Indexing audit", description="Inspect your most visible pages and get a prioritised fix list.")
    def indexing_audit(site_url: str = "", source: str = "top_pages") -> str:
        return _clean(f"""Run an indexing audit.
    {_site_line(site_url)}
    URL source: {source or 'top_pages'}

    Steps:
    1. skill_read("indexing-audit").
    2. get_index_coverage(source="{source or 'top_pages'}", limit=20) for the overall picture.
    3. check_indexing_issues on the URLs that are not PASS or have canonical mismatches.
    4. inspect_url_enhanced on the 3 most important problem URLs.
    5. Output a prioritised list: Critical (not indexed but has impressions) > High (canonical mismatch) > Medium (robots/noindex/fetch) > Low.

    {_QUIRKS}""")


    @mcp.prompt(name="analyze-brand-visibility", title="Analyze brand visibility", description="Branded vs non-branded share, CTR and positions.")
    def analyze_brand_visibility(site_url: str = "", brand_terms: str = "") -> str:
        terms = brand_terms.strip() or "(ask the user for the brand name plus common variants and misspellings)"
        return _clean(f"""Analyze brand visibility in Google Search.
    {_site_line(site_url)}
    Brand terms: {terms}

    Steps:
    1. skill_read("brand-visibility").
    2. get_brand_vs_nonbrand(brand_terms="<terms>").
    3. Report branded share of clicks/impressions, branded vs non-branded CTR, and the average position of exact brand queries (should be close to 1 — worse means a problem).
    4. List misspellings or brand + product queries ranking poorly and what to do about them.

    {_QUIRKS}""")


    @mcp.prompt(name="diagnose-traffic-drop", title="Diagnose a traffic drop", description="Localise a search traffic drop: when, which segment, and the likely cause.")
    def diagnose_traffic_drop(site_url: str = "", drop_period: str = "") -> str:
        period = drop_period.strip() or "(ask roughly when the drop started; default to the last 14 days vs the 14 days before)"
        return _clean(f"""Diagnose a Google Search traffic drop.
    {_site_line(site_url)}
    Drop period: {period}

    Steps:
    1. skill_read("diagnose-traffic-drop").
    2. get_performance_overview(days=90) — confirm the shape and the start date; did clicks, impressions or both fall?
    3. compare_search_periods for matched windows, one dimension at a time: query, page, device, country.
    4. get_search_analytics(dimensions="searchAppearance") for both windows to spot lost rich results.
    5. Classify: impressions down at stable position = indexing/coverage; position down = ranking loss; CTR down at stable position = SERP feature change.
    6. get_sitemaps and get_index_coverage for the top losing pages.
    7. Report the drop's shape, losing segment, most likely cause and the fix, with the numbers.

    {_QUIRKS}""")
