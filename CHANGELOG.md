# Changelog

All notable changes to Sam GSC MCP. Dates are YYYY-MM-DD. This project follows [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-10-24

First release.

### Added — core
- **Auth:** OAuth (browser sign-in, token stored in the OS config folder), service account key, `GSC_SKIP_OAUTH`,
  `reauthenticate`, fail-fast errors for wrong credential paths, `GOOGLE_APPLICATION_CREDENTIALS` support.
- **Properties:** `list_properties`, `get_site_details`, `add_site`, `delete_site`.
- **Analytics:** `get_search_analytics`, `get_advanced_search_analytics` (25k rows, pagination, client-side sorting,
  multi-filter AND), `get_performance_overview`, `compare_search_periods`, `get_search_by_page_query`,
  `get_site_summary` (period vs previous period), `summary_only` totals, `searchAppearance`, regex operators,
  `discover` / `googleNews` search types, `GSC_DATA_STATE`.
- **Inspection:** `inspect_url_enhanced` (with rich-result issues from the correct API path), `batch_url_inspection`
  and `check_indexing_issues` (concurrent), `check_url_status`, `get_index_coverage`, `get_mobile_issues`.
- **Sitemaps:** `get_sitemaps`, `list_sitemaps_enhanced`, `get_sitemap_details`, `submit_sitemap`, `delete_sitemap`,
  `manage_sitemaps`.
- **Discovery & skills:** `get_capabilities`, `list_available_dimensions`, `list_available_metrics`, `skills_list`,
  `skill_read`, skills exposed as MCP resources (`skill://…`), workflow prompts, tool annotations.
- **Recovery:** `setup_gsc_access` with interactive prompts (MCP elicitation) on supporting clients, guided error messages.
- **Ops:** `check_for_updates`, `GSC_ALLOW_DESTRUCTIVE` safety flag, SSE / streamable HTTP transport, Dockerfile.

### Added — SEO power features
- **SEO insight tools:** `find_striking_distance_keywords`, `find_keyword_cannibalization`, `get_brand_vs_nonbrand`,
  `find_low_ctr_opportunities` — computed server-side, so the AI gets ranked answers instead of raw rows.
- **`get_hourly_performance`** — Search Analytics hourly data (`HOUR` + `HOURLY_ALL`, last ~10 days).
- **`export_search_analytics`** — auto-paginated CSV export (up to 500,000 rows).
- **Real Indexing API** — `request_indexing` / `get_indexing_status` (opt-in via `GSC_ENABLE_INDEXING_API`).
- **Real coverage reports** — `get_index_coverage` / `get_mobile_issues` sample URLs from top pages, a sitemap
  (read directly, including sitemap indexes and `.gz`) or your list, then group live URL Inspection results.
- **Property auto-matching** — `example.com`, `www.example.com` or a URL without trailing slash resolves to the
  matching `sc-domain:` / URL-prefix property. `site_url` is optional everywhere when `GSC_SITE_URL` is set.
- **Application Default Credentials** (`GSC_AUTH_MODE=adc` / `GSC_USE_ADC`).
- **`GSC_READ_ONLY`** — read-only OAuth scope and every write tool hidden.
- **`GSC_TOOLSETS` / `GSC_DISABLED_TOOLS`** — load only the tool groups you need (useful for clients with tool limits).
- **`GSC_COMPAT_ALIASES`** — optional aliases (`list_sites`, `list_gsc_sites`, `get_performance_data`,
  `get_url_inspection_result`, `get_sitemap_data`, `submit_url`) so prompts written with these common tool names keep working.
- **11 SEO skills:** seo-weekly-report, keyword-cannibalization, indexing-audit, content-opportunities,
  brand-visibility, citation-opportunities, intent-efficiency, intent-segmentation, search-appearance-audit,
  diagnose-traffic-drop, content-decay. **6 prompts:** seo-weekly-report, content-opportunities,
  cannibalization-check, indexing-audit, analyze-brand-visibility, diagnose-traffic-drop.
- **Claude Code plugin + marketplace manifest** (`.claude-plugin/`), example configs for Claude Desktop, Claude Code,
  Cursor, VS Code, Codex CLI, Gemini CLI and Docker Compose.
- Works on **both MCP Python SDK lines** (1.x `FastMCP` and 2.x `MCPServer`) — no more breakage when the SDK major
  version changes.

### Quality details
- CTR is returned consistently as a **percentage** in every tool (`ctr_unit: "percent"`).
- Robots.txt blocks are detected from the real API values (`DISALLOWED`, `BLOCKED_ROBOTS_TXT`); never-crawled URLs are
  no longer reported as fetch errors.
- `compare_search_periods` now defaults to "last 28 days vs previous 28", returns period totals, and separates new,
  lost, gaining and losing items.
- The OAuth consent URL is never printed to stdout (which would corrupt the MCP stdio stream); on headless machines it is
  written to the MCP log instead of failing.
- Saved token is checked for the required scopes (e.g. after enabling the Indexing API) and re-requested if needed.
- Google API calls retry automatically on 429/5xx (`GSC_API_RETRIES`).
- No telemetry.
