---
name: brand-visibility
title: Brand Visibility
description: Compare branded vs non-branded search performance to see whether people search for you by name (a destination) or only find you through generic queries (a reference). Use for brand share, branded traffic, brand awareness or non-brand growth questions.
---

# Brand Visibility

## Steps

1. Ask for the brand name plus variants and common misspellings (e.g. `acme, acme corp, akme`).
2. `get_brand_vs_nonbrand(brand_terms="<comma list>", days=28, top_n=15)`.
   - Uses a case-insensitive regex filter: branded = `includingRegex`, non-branded = `excludingRegex`.
3. Trend: run it for `days=28` and compare with `compare_search_periods(filters=[{"dimension":"query","operator":"includingRegex","expression":"<brand_regex from step 2>"}])`.
4. Exact brand queries: `get_search_analytics(dimensions="query", filters=[{"dimension":"query","operator":"includingRegex","expression":"(?i)^<brand>$"}])`.

## How to read it

| Signal | Meaning |
|---|---|
| Branded click share > 50% | Strong brand demand; growth depends on non-brand SEO |
| Branded click share < 10% | Mostly generic discovery — build brand + topical authority |
| Exact brand query position > 1.5 | Something outranks you for your own name — check SERP, sitelinks, GBP, review sites |
| Branded CTR < 30% | SERP features, ads or competitors are taking brand clicks |

## Output

Summary table (clicks, impressions, CTR, position for each segment, share %), top branded and non-branded queries, and 3 actions.

## Notes

Anonymised queries are dropped from query-filtered results, so the two segments can add up to less than the site total.
