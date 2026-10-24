from datetime import date, timedelta

import pytest

from sam_gsc_mcp import gsc, inspection, reference, skills
from sam_gsc_mcp.gsc import ToolError


def test_normalize_dimensions_accepts_many_shapes():
    assert gsc.normalize_dimensions("query, page") == ["query", "page"]
    assert gsc.normalize_dimensions(["Query", "search_appearance"]) == ["query", "searchAppearance"]
    assert gsc.normalize_dimensions('["date","device"]') == ["date", "device"]
    assert gsc.normalize_dimensions(None) == ["query"]
    with pytest.raises(ToolError):
        gsc.normalize_dimensions("keyword")


def test_normalize_filters_and_operators():
    out = gsc.normalize_filters('[{"dimension":"device","operator":"EQUALS","expression":"mobile"}]')
    assert out == [{"dimension": "device", "operator": "equals", "expression": "MOBILE"}]
    out = gsc.normalize_filters(None, "query", "regex", "(?i)gst")
    assert out[0]["operator"] == "includingRegex"
    out = gsc.normalize_filters([{"dimension": "country", "operator": "equals", "expression": "IND"}])
    assert out[0]["expression"] == "ind"
    with pytest.raises(ToolError):
        gsc.normalize_filters([{"dimension": "date", "expression": "x"}])
    with pytest.raises(ToolError):
        gsc.normalize_filters([{"dimension": "query", "operator": "like", "expression": "x"}])


def test_search_type_mapping():
    assert gsc.normalize_search_type("Google News") == "googleNews"
    assert gsc.normalize_search_type(None) == "web"
    with pytest.raises(ToolError):
        gsc.normalize_search_type("shopping")


def test_date_range_defaults_and_explicit():
    start, end, n = gsc.date_range(28, None, None, "all")
    assert n == 28
    assert end == (date.today() - timedelta(days=1)).isoformat()
    s2, e2, n2 = gsc.date_range(28, "2026-01-01", "2026-01-31", "all")
    assert (s2, e2, n2) == ("2026-01-01", "2026-01-31", 31)
    with pytest.raises(ToolError):
        gsc.date_range(28, "2026-02-01", "2026-01-01", "all")
    assert gsc.previous_range("2026-01-29", "2026-02-25") == ("2026-01-01", "2026-01-28")


def test_build_query_hour_switches_data_state():
    body = gsc.build_query("2026-01-01", "2026-01-02", ["hour"], row_limit=99999)
    assert body["dimensions"] == ["HOUR"]
    assert body["dataState"] == "HOURLY_ALL"
    assert body["rowLimit"] == 25000
    body = gsc.build_query("2026-01-01", "2026-01-02", [], filters=[{"dimension": "page", "operator": "equals", "expression": "x"}])
    assert "dimensions" not in body
    assert body["dimensionFilterGroups"][0]["filters"][0]["expression"] == "x"


def test_format_row_and_totals():
    row = gsc.format_row({"keys": ["gst"], "clicks": 10, "impressions": 200, "ctr": 0.05, "position": 3.456}, ["query"])
    assert row == {"query": "gst", "clicks": 10, "impressions": 200, "ctr": 5.0, "position": 3.5}
    t = gsc.totals([{"clicks": 10, "impressions": 100, "position": 2}, {"clicks": 0, "impressions": 300, "position": 10}])
    assert t["ctr"] == 2.5 and t["position"] == 8.0


def test_site_candidates():
    c = gsc._candidates("www.Example.com")
    assert "sc-domain:example.com" in c and "https://www.example.com/" in c
    assert gsc._candidates("https://example.com")[1] == "https://example.com/"


def test_resolve_site_auto_matches(fake, monkeypatch):
    fake.sites_list = [{"siteUrl": "https://www.example.com/", "permissionLevel": "siteFullUser"}]
    assert gsc.resolve_site("example.com") == "https://www.example.com/"
    assert gsc.resolve_site("https://www.example.com") == "https://www.example.com/"
    with pytest.raises(ToolError):
        gsc.resolve_site(None)


def test_parse_urls():
    assert gsc.parse_urls("https://a.com/1\nhttps://a.com/2, https://a.com/3") == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]
    assert gsc.parse_urls(["https://a.com/x"]) == ["https://a.com/x"]


def test_rich_results_and_classify():
    resp = {
        "inspectionResult": {
            "indexStatusResult": {
                "verdict": "NEUTRAL",
                "coverageState": "Crawled - currently not indexed",
                "robotsTxtState": "ALLOWED",
                "indexingState": "BLOCKED_BY_META_TAG",
                "pageFetchState": "SUCCESSFUL",
                "googleCanonical": "https://a.com/x",
                "userCanonical": "https://a.com/y",
            },
            "richResultsResult": {
                "verdict": "FAIL",
                "detectedItems": [{"richResultType": "FAQ", "items": [{"name": "faq", "issues": [{"severity": "ERROR", "issueMessage": "Missing field"}]}]}],
            },
        }
    }
    row = inspection.summarize("https://a.com/y", "sc-domain:a.com", resp, full=True)
    assert row["canonical_mismatch"] is True
    assert row["rich_results"]["issues"][0]["message"] == "Missing field"
    buckets = inspection.classify(row)
    assert {"not_indexed", "canonical_issues", "noindex", "rich_result_issues"} <= set(buckets)
    assert "fetch_issues" not in buckets


def test_sitemap_parsing():
    urlset = b"""<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url><loc>https://a.com/1</loc></url><url><loc> https://a.com/2 </loc></url></urlset>"""
    locs, is_index = inspection._locs(urlset)
    assert locs == ["https://a.com/1", "https://a.com/2"] and not is_index
    idx = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>https://a.com/s1.xml</loc></sitemap></sitemapindex>"""
    assert inspection._locs(idx) == (["https://a.com/s1.xml"], True)


def test_expected_ctr_curve_is_monotonic():
    values = [reference.expected_ctr(p) for p in (1, 2, 3.5, 7, 10, 15)]
    assert values == sorted(values, reverse=True)


def test_skills_bundle_and_traversal_guard():
    items = skills.list_skills()
    ids = {s["id"] for s in items}
    assert {"seo-weekly-report", "keyword-cannibalization", "indexing-audit", "content-opportunities",
            "brand-visibility", "diagnose-traffic-drop"} <= ids
    assert all(s["description"] for s in items)
    assert skills.read_skill("brand_visibility.md")["id"] == "brand-visibility"
    assert skills.read_skill("../../etc/passwd") is None
