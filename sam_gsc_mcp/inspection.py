"""URL Inspection API helpers and sitemap XML reading."""

from __future__ import annotations

import asyncio
import gzip
import io
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Optional

from . import config as cfg
from . import gsc
from .gsc import fmt_time

log = logging.getLogger("sam_gsc_mcp")

USER_AGENT = "SamGSCMCP/1.0 (+https://github.com/krishanthsam/sam-gsc-mcp)"
MAX_SITEMAP_BYTES = 50 * 1024 * 1024


def rich_results_summary(inspection: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Rich-result verdict, detected types and the nested issue list.

    Issues live under detectedItems[].items[].issues[] with key issueMessage.
    """
    rich = inspection.get("richResultsResult")
    if not rich:
        return None
    detected = rich.get("detectedItems", []) or []
    return {
        "verdict": rich.get("verdict", "UNKNOWN"),
        "detected_types": [d.get("richResultType", "Unknown") for d in detected],
        "issues": [
            {
                "type": d.get("richResultType", "Unknown"),
                "item": item.get("name"),
                "severity": issue.get("severity"),
                "message": issue.get("issueMessage"),
            }
            for d in detected
            for item in d.get("items", []) or []
            for issue in item.get("issues", []) or []
        ],
    }


def mobile_summary(inspection: dict[str, Any]) -> Optional[dict[str, Any]]:
    mob = inspection.get("mobileUsabilityResult")
    if not mob:
        return None
    return {
        "verdict": mob.get("verdict", "UNKNOWN"),
        "issues": [
            {"type": i.get("issueType"), "severity": i.get("severity"), "message": i.get("message")}
            for i in mob.get("issues", []) or []
        ],
    }


def inspect_raw(site_url: str, page_url: str, language_code: Optional[str] = None) -> dict[str, Any]:
    body: dict[str, Any] = {"inspectionUrl": page_url, "siteUrl": site_url}
    if language_code:
        body["languageCode"] = language_code
    return gsc.execute(gsc.service().urlInspection().index().inspect(body=body)) or {}


def summarize(page_url: str, site_url: str, response: dict[str, Any], *, full: bool = True, include_raw: bool = False) -> dict[str, Any]:
    inspection = response.get("inspectionResult", {}) or {}
    idx = inspection.get("indexStatusResult", {}) or {}
    out: dict[str, Any] = {
        "url": page_url,
        "index_verdict": idx.get("verdict", "UNKNOWN"),
        "is_indexed": idx.get("verdict") == "PASS",
        "coverage_state": idx.get("coverageState"),
        "last_crawled": fmt_time(idx.get("lastCrawlTime")),
        "page_fetch_state": idx.get("pageFetchState"),
        "robots_txt_state": idx.get("robotsTxtState"),
        "indexing_state": idx.get("indexingState"),
        "google_canonical": idx.get("googleCanonical"),
        "user_canonical": idx.get("userCanonical"),
        "crawled_as": idx.get("crawledAs"),
    }
    gc, uc = out["google_canonical"], out["user_canonical"]
    out["canonical_mismatch"] = bool(gc and uc and gc != uc)
    if full:
        out["site_url"] = site_url
        out["inspection_result_link"] = inspection.get("inspectionResultLink")
        out["sitemaps"] = (idx.get("sitemap") or [])[:5]
        out["referring_urls"] = (idx.get("referringUrls") or [])[:5]
        out["rich_results"] = rich_results_summary(inspection)
        out["mobile_usability"] = mobile_summary(inspection)
        amp = inspection.get("ampResult")
        if amp:
            out["amp"] = {"verdict": amp.get("verdict"), "amp_url": amp.get("ampUrl"), "issues": amp.get("issues", [])}
    else:
        out["rich_results"] = rich_results_summary(inspection)
    if include_raw:
        out["raw_response"] = response
    return out


def inspect_one(site_url: str, page_url: str, full: bool = False, language_code: Optional[str] = None) -> dict[str, Any]:
    """Never raises — failures come back as an error row so one URL can't sink a batch."""
    try:
        resp = inspect_raw(site_url, page_url, language_code)
        if not resp or "inspectionResult" not in resp:
            return {"url": page_url, "error": "No inspection data returned"}
        return summarize(page_url, site_url, resp, full=full)
    except Exception as exc:
        status, message, _ = gsc._http_details(exc)
        return {"url": page_url, "error": f"HTTP {status}: {message}" if status else str(exc)}


async def inspect_many(site_url: str, urls: list[str], full: bool = False) -> list[dict[str, Any]]:
    """Inspect concurrently (blocking client runs in worker threads); keeps input order."""
    sem = asyncio.Semaphore(cfg.SETTINGS.inspection_concurrency)

    async def _run(u: str) -> dict[str, Any]:
        async with sem:
            return await asyncio.to_thread(inspect_one, site_url, u, full)

    return list(await asyncio.gather(*[_run(u) for u in urls]))


def classify(row: dict[str, Any]) -> list[str]:
    """Issue buckets for one summarized row."""
    if "error" in row:
        return ["errors"]
    buckets = []
    coverage = (row.get("coverage_state") or "").lower()
    if row.get("index_verdict") != "PASS" or "not indexed" in coverage or "excluded" in coverage:
        buckets.append("not_indexed")
    else:
        buckets.append("indexed")
    if row.get("canonical_mismatch"):
        buckets.append("canonical_issues")
    if row.get("robots_txt_state") in ("DISALLOWED", "BLOCKED") or row.get("page_fetch_state") == "BLOCKED_ROBOTS_TXT":
        buckets.append("robots_blocked")
    fetch = row.get("page_fetch_state")
    if fetch and fetch not in ("SUCCESSFUL", "PAGE_FETCH_STATE_UNSPECIFIED"):
        buckets.append("fetch_issues")
    if row.get("indexing_state") and row["indexing_state"] not in ("INDEXING_ALLOWED", "INDEXING_STATE_UNSPECIFIED"):
        buckets.append("noindex")
    rich = row.get("rich_results") or {}
    if rich.get("issues"):
        buckets.append("rich_result_issues")
    return buckets


# --------------------------------------------------------------------------- sitemaps

def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 - user-supplied sitemap URL
        data = resp.read(MAX_SITEMAP_BYTES + 1)
        encoding = resp.headers.get("Content-Encoding", "")
    if len(data) > MAX_SITEMAP_BYTES:
        raise ValueError("Sitemap larger than 50 MB")
    if encoding == "gzip" or url.endswith(".gz") or data[:2] == b"\x1f\x8b":
        data = gzip.GzipFile(fileobj=io.BytesIO(data)).read(MAX_SITEMAP_BYTES + 1)
    return data


def _locs(xml_bytes: bytes) -> tuple[list[str], bool]:
    """Return (<loc> values, is_index)."""
    # Strip any DOCTYPE to avoid entity expansion tricks.
    text = re.sub(rb"<!DOCTYPE[^>]*>", b"", xml_bytes, flags=re.IGNORECASE)
    root = ET.fromstring(text)
    tag = root.tag.split("}")[-1].lower()
    locs = [el.text.strip() for el in root.iter() if el.tag.split("}")[-1].lower() == "loc" and el.text]
    return locs, tag == "sitemapindex"


def urls_from_sitemap(sitemap_url: str, limit: int = 50) -> list[str]:
    """Read page URLs from a sitemap or sitemap index (follows one level of children)."""
    locs, is_index = _locs(_fetch(sitemap_url))
    if not is_index:
        return locs[:limit]
    out: list[str] = []
    for child in locs:
        if len(out) >= limit:
            break
        try:
            child_locs, child_is_index = _locs(_fetch(child))
            if not child_is_index:
                out.extend(child_locs[: limit - len(out)])
        except Exception as exc:
            log.warning("Skipping child sitemap %s: %s", child, exc)
    return out
