---
name: indexing-audit
title: Indexing Audit
description: Audit whether Google has indexed your most important pages and produce a prioritised fix list. Use when asked about crawling, indexing problems, "is my page indexed", canonical issues, noindex or robots.txt blocks.
---

# Indexing Audit

Check the indexing status of the pages that matter most and turn the results into a fix list.

## Steps

1. Confirm the property with `list_properties`.
2. Overview: `get_index_coverage(source="top_pages", limit=20)` — groups URLs by Google's coverage state.
   - For new or low-traffic sites use `source="sitemap"` (reads URLs from your submitted sitemap).
3. Detail: `check_indexing_issues(urls=<URLs that are not PASS or have canonical mismatches>)`.
   Max 10 URLs per call by default (raise with `GSC_MAX_BATCH_URLS`).
4. Deep dive on the 3 most important problem pages: `inspect_url_enhanced(page_url=...)`.
5. Check `get_sitemaps` for errors and make sure problem URLs are in a sitemap.

## Bucket meanings

| Bucket | What it means | Typical fix |
|---|---|---|
| not_indexed — "Crawled - currently not indexed" | Google saw it but didn't think it was worth indexing | Improve content depth/uniqueness, add internal links |
| not_indexed — "Discovered - currently not indexed" | Known but not crawled yet | Internal links, sitemap, reduce crawl waste |
| canonical_issues | Google picked a different canonical | Align rel=canonical, internal links, redirects and sitemap URLs |
| robots_blocked | robots.txt disallows the URL | Remove the Disallow rule if the page should rank |
| noindex | Meta robots or X-Robots-Tag noindex | Remove the tag on pages that should rank |
| fetch_issues | 404, soft 404, 5xx, redirect error | Fix the server response / redirect chain |
| rich_result_issues | Structured data errors | Fix the schema items listed |

## Output format

1. **Critical** — not indexed but the page has (or should have) impressions
2. **High** — canonical mismatches on important pages
3. **Medium** — robots / noindex / fetch problems
4. **Low** — soft exclusions on low-value pages

End with a table: URL | verdict | coverage state | issue | recommended action.

## Notes

- URL Inspection quota: 2,000 calls/day and 600/minute per property.
- After fixing, use "Request indexing" in Search Console (or `request_indexing` for JobPosting/BroadcastEvent pages).
