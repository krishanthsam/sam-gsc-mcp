import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import parse

from sam_gsc_mcp import config as cfg
from sam_gsc_mcp import server

ROOT = Path(__file__).resolve().parents[1]


async def call(name, args=None):
    return parse(await server.mcp.call_tool(name, args or {}))


def _rows_handler(table):
    """table: dict of tuple(dimensions) -> list of rows."""

    def handler(site, body):
        dims = tuple(body.get("dimensions", []))
        return {"rows": table.get(dims, [])}

    return handler


async def test_tool_inventory():
    names = {t.name for t in await server.mcp.list_tools()}
    expected = {
        "get_capabilities", "setup_gsc_access", "reauthenticate", "check_for_updates", "get_creator_info",
        "list_available_dimensions", "list_available_metrics", "list_filter_options", "skills_list", "skill_read",
        "list_properties", "get_site_details", "add_site", "delete_site",
        "get_search_analytics", "get_advanced_search_analytics", "get_performance_overview", "get_site_summary",
        "compare_search_periods", "get_search_by_page_query", "get_hourly_performance", "export_search_analytics",
        "find_striking_distance_keywords", "find_keyword_cannibalization", "get_brand_vs_nonbrand", "find_low_ctr_opportunities",
        "inspect_url_enhanced", "check_url_status", "batch_url_inspection", "check_indexing_issues", "get_index_coverage", "get_mobile_issues",
        "get_sitemaps", "list_sitemaps_enhanced", "get_sitemap_details", "submit_sitemap", "delete_sitemap", "manage_sitemaps",
    }
    assert expected <= names
    assert "request_indexing" not in names  # opt-in
    assert "list_sites" not in names  # aliases opt-in
    assert len(server.TOOL_REGISTRY) == 46


async def test_search_analytics_formats_ctr_as_percent(fake):
    fake.query_handler = _rows_handler({("query",): [{"keys": ["gst registration"], "clicks": 12, "impressions": 400, "ctr": 0.03, "position": 4.2}]})
    data = await call("get_search_analytics", {"site_url": "example.com", "dimensions": "query", "row_limit": 5})
    assert data["site_url"] == "sc-domain:example.com"  # auto-matched
    assert data["rows"][0] == {"query": "gst registration", "clicks": 12, "impressions": 400, "ctr": 3.0, "position": 4.2}
    body = fake.calls[-1][2]
    assert body["rowLimit"] == 5 and body["type"] == "web" and body["dataState"] == "all"


async def test_summary_only(fake):
    fake.query_handler = _rows_handler({(): [{"clicks": 50, "impressions": 1000, "ctr": 0.05, "position": 7}]})
    data = await call("get_search_analytics", {"site_url": "sc-domain:example.com", "summary_only": True})
    assert data["summary"]["clicks"] == 50 and data["summary"]["ctr"] == 5.0


async def test_advanced_sorting_and_pagination(fake):
    rows = [{"keys": [f"q{i}"], "clicks": i, "impressions": 100 - i, "ctr": 0.01, "position": 20 - i} for i in range(5)]
    fake.query_handler = _rows_handler({("query",): rows})
    data = await call("get_advanced_search_analytics", {"site_url": "sc-domain:example.com", "row_limit": 5, "sort_by": "position", "sort_direction": "ascending"})
    assert [r["position"] for r in data["rows"]] == sorted(r["position"] for r in data["rows"])
    assert data["pagination"]["has_more"] is True and data["pagination"]["next_start_row"] == 5


async def test_invalid_dimension_is_friendly(fake):
    data = await call("get_search_analytics", {"site_url": "sc-domain:example.com", "dimensions": "keyword"})
    assert "Invalid dimension" in data["error"]


async def test_compare_periods_direction(fake):
    def handler(site, body):
        if body["startDate"] > "2026-02-01":
            return {"rows": [{"keys": ["a"], "clicks": 30, "impressions": 300, "ctr": 0.1, "position": 2.0}]}
        return {"rows": [{"keys": ["a"], "clicks": 10, "impressions": 200, "ctr": 0.05, "position": 5.0},
                         {"keys": ["b"], "clicks": 5, "impressions": 50, "ctr": 0.1, "position": 9.0}]}

    fake.query_handler = handler
    data = await call("compare_search_periods", {"site_url": "sc-domain:example.com", "period1_start": "2026-02-02", "period1_end": "2026-02-28",
                                                 "period2_start": "2026-01-01", "period2_end": "2026-01-27"})
    a = next(i for i in data["biggest_movers"] if i["query"] == "a")
    assert a["click_diff"] == 20 and a["click_pct"] == 200.0 and a["position_diff"] == 3.0
    assert data["lost_items"] == 1


async def test_cannibalization(fake):
    fake.query_handler = _rows_handler({("query", "page"): [
        {"keys": ["gst", "https://a.com/gst"], "clicks": 40, "impressions": 800, "ctr": 0.05, "position": 3},
        {"keys": ["gst", "https://a.com/blog/gst"], "clicks": 5, "impressions": 400, "ctr": 0.0125, "position": 8},
        {"keys": ["itr", "https://a.com/itr"], "clicks": 9, "impressions": 500, "ctr": 0.018, "position": 5},
    ]})
    data = await call("find_keyword_cannibalization", {"site_url": "sc-domain:example.com"})
    assert data["conflicts_found"] == 1
    c = data["conflicts"][0]
    assert c["query"] == "gst" and c["suggested_primary_page"] == "https://a.com/gst" and c["severity"] == "high"


async def test_striking_distance_and_low_ctr(fake):
    fake.query_handler = _rows_handler({("query", "page"): [
        {"keys": ["near", "https://a.com/1"], "clicks": 2, "impressions": 900, "ctr": 0.002, "position": 9},
        {"keys": ["top", "https://a.com/2"], "clicks": 3, "impressions": 1200, "ctr": 0.0025, "position": 1.2},
        {"keys": ["far", "https://a.com/3"], "clicks": 0, "impressions": 900, "ctr": 0.0, "position": 45},
    ]})
    sd = await call("find_striking_distance_keywords", {"site_url": "sc-domain:example.com"})
    assert [r["query"] for r in sd["rows"]] == ["near"]
    low = await call("find_low_ctr_opportunities", {"site_url": "sc-domain:example.com"})
    assert low["rows"][0]["query"] == "top" and "silent reference" in low["rows"][0]["pattern"]


async def test_brand_split_uses_regex(fake):
    def handler(site, body):
        op = body["dimensionFilterGroups"][0]["filters"][0]["operator"]
        clicks = 70 if op == "includingRegex" else 30
        return {"rows": [{"keys": ["x"] if body.get("dimensions") else [], "clicks": clicks, "impressions": clicks * 10, "ctr": 0.1, "position": 2}]}

    fake.query_handler = handler
    data = await call("get_brand_vs_nonbrand", {"site_url": "sc-domain:example.com", "brand_terms": "Acme Corp, acme"})
    assert data["branded_click_share_pct"] == 70.0
    assert data["brand_regex"] == "(?i)(Acme\\ Corp|acme)"


async def test_check_indexing_issues_buckets(fake):
    def inspect(body):
        url = body["inspectionUrl"]
        ok = url.endswith("/ok")
        return {"inspectionResult": {"indexStatusResult": {
            "verdict": "PASS" if ok else "NEUTRAL",
            "coverageState": "Submitted and indexed" if ok else "Discovered - currently not indexed",
            "robotsTxtState": "ALLOWED", "pageFetchState": "SUCCESSFUL" if ok else "PAGE_FETCH_STATE_UNSPECIFIED",
            "indexingState": "INDEXING_ALLOWED"}}}

    fake.inspect_handler = inspect
    data = await call("check_indexing_issues", {"site_url": "sc-domain:example.com", "urls": "https://example.com/ok\nhttps://example.com/new"})
    assert data["summary"]["indexed"] == 1 and data["summary"]["not_indexed"] == 1
    assert "fetch_issues" not in data["summary"]


async def test_batch_limit(fake):
    urls = "\n".join(f"https://example.com/{i}" for i in range(cfg.SETTINGS.max_batch_urls + 1))
    data = await call("batch_url_inspection", {"site_url": "sc-domain:example.com", "urls": urls})
    assert "Too many URLs" in data["error"]


async def test_sitemaps_and_destructive_guard(fake):
    fake.sitemap_list = [{"path": "https://example.com/sitemap.xml", "errors": "2", "warnings": "0", "isPending": False,
                          "contents": [{"type": "web", "submitted": "120"}]}]
    data = await call("get_sitemaps", {"site_url": "sc-domain:example.com"})
    assert data["with_errors"] == 1 and data["sitemaps"][0]["urls_submitted"] == 120
    sub = await call("submit_sitemap", {"site_url": "sc-domain:example.com", "sitemap_url": "https://example.com/new.xml"})
    assert sub["status"] == "submitted" and ("submit", "https://example.com/new.xml") in fake.calls
    blocked = await call("delete_sitemap", {"site_url": "sc-domain:example.com", "sitemap_url": "https://example.com/sitemap.xml"})
    assert "Safety" in blocked["error"]


async def test_export_csv(fake, tmp_path, monkeypatch):
    monkeypatch.setattr(cfg.SETTINGS, "export_dir", tmp_path)
    fake.query_handler = _rows_handler({("query", "page"): [{"keys": ["q", "https://a.com"], "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 3}]})
    data = await call("export_search_analytics", {"site_url": "sc-domain:example.com"})
    text = Path(data["file"]).read_text(encoding="utf-8-sig")
    assert text.splitlines()[0] == "query,page,clicks,impressions,ctr,position"
    assert data["rows_written"] == 1


async def test_http_404_message(fake):
    from googleapiclient.errors import HttpError

    class Resp(dict):
        status = 404
        reason = "Not Found"

    def boom(site, body):
        raise HttpError(Resp(), b'{"error":{"message":"not found","errors":[{"reason":"notFound"}]}}')

    fake.query_handler = boom
    data = await call("get_search_analytics", {"site_url": "https://nope.com/"})
    assert "not found (404)" in data["error"] and data["how_to_fix"]


def test_toolsets_env_filters_registration():
    env = dict(os.environ, GSC_TOOLSETS="analytics", GSC_READ_ONLY="true", GSC_CONFIG_DIR=str(ROOT / ".pytest-config"))
    code = (
        "import asyncio,json;from sam_gsc_mcp import server;"
        "print(json.dumps(sorted(t.name for t in asyncio.run(server.mcp.list_tools()))))"
    )
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, cwd=ROOT, check=True)
    names = set(json.loads(out.stdout.strip().splitlines()[-1]))
    assert "get_search_analytics" in names and "get_capabilities" in names
    assert "inspect_url_enhanced" not in names and "submit_sitemap" not in names
    assert "setup_gsc_access" not in names  # write tool hidden in read-only mode


def test_config_aliases(monkeypatch, tmp_path):
    key = tmp_path / "sa.json"
    key.write_text('{"type":"service_account","client_email":"bot@p.iam.gserviceaccount.com"}')
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(key))
    monkeypatch.setenv("GSC_SKIP_OAUTH", "true")
    monkeypatch.setenv("GSC_SITE_URL", "sc-domain:example.com")
    s = cfg.load_settings()
    assert s.credentials_path == str(key) and s.auth_mode == "service_account" and s.site_url == "sc-domain:example.com"
    from sam_gsc_mcp import auth

    assert auth.inspect_credentials_file(str(key)) == ("service_account", "bot@p.iam.gserviceaccount.com")
