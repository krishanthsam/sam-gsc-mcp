---
name: intent-efficiency
title: Intent Efficiency
description: Split search traffic by user intent — informational, commercial, transactional and navigational — to see which stage of the buyer journey brings clicks and where CTR is weak. Use for funnel, intent mix or "what kind of searches bring us traffic" questions.
---

# Intent Efficiency

## Steps

1. `get_advanced_search_analytics(dimensions="query", row_limit=5000)` (paginate with `start_row` for bigger sites, or `export_search_analytics` for a CSV).
2. Classify each query (first match wins):
   - **Transactional** — buy, price, pricing, cost, fees, charges, hire, near me, book, order, quote, apply, online, service, agency, consultant
   - **Commercial investigation** — best, top, vs, versus, compare, review, alternative, list of
   - **Informational** — how, what, why, when, which, who, guide, tutorial, meaning, example, ideas, tips, checklist, process, documents required
   - **Navigational** — brand names, login, contact, specific product names
   - **Other** — everything else
3. Sum clicks and impressions per bucket; compute CTR (clicks ÷ impressions) and impression-weighted average position.

## Output

| Intent | Queries | Clicks | Click share | Impressions | CTR % | Avg pos. |

Then:
- Which intent drives revenue-relevant traffic vs. which only drives visits.
- Buckets with high impressions and low CTR → title/meta work.
- Missing commercial/transactional coverage → new service or comparison pages.

## Tip

Add local or industry words to the lists (e.g. "registration", "filing", "consultant in chennai") to fit the site.
