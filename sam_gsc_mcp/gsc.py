"""Shared helpers: request building, site resolution, formatting and errors."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from . import auth
from . import config as cfg

log = logging.getLogger("sam_gsc_mcp")

VALID_DIMENSIONS = {
    "query": "query",
    "page": "page",
    "url": "page",
    "country": "country",
    "device": "device",
    "date": "date",
    "searchappearance": "searchAppearance",
    "search_appearance": "searchAppearance",
    "appearance": "searchAppearance",
    "hour": "hour",
}
FILTERABLE_DIMENSIONS = {"query", "page", "country", "device", "searchAppearance"}
OPERATOR_MAP = {
    "equals": "equals",
    "eq": "equals",
    "=": "equals",
    "notequals": "notEquals",
    "not_equals": "notEquals",
    "ne": "notEquals",
    "!=": "notEquals",
    "contains": "contains",
    "notcontains": "notContains",
    "not_contains": "notContains",
    "includingregex": "includingRegex",
    "including_regex": "includingRegex",
    "regex": "includingRegex",
    "excludingregex": "excludingRegex",
    "excluding_regex": "excludingRegex",
    "notregex": "excludingRegex",
}
SEARCH_TYPE_MAP = {
    "web": "web",
    "image": "image",
    "images": "image",
    "video": "video",
    "videos": "video",
    "news": "news",
    "discover": "discover",
    "googlenews": "googleNews",
    "google_news": "googleNews",
    "google news": "googleNews",
}


class ToolError(Exception):
    """A user-facing error with optional fix-it steps."""

    def __init__(self, message: str, how_to_fix: Optional[list[str]] = None):
        super().__init__(message)
        self.message = message
        self.how_to_fix = how_to_fix or []


# --------------------------------------------------------------------------- output

def dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))


def error_payload(message: str, how_to_fix: Optional[list[str]] = None, **extra: Any) -> str:
    payload: dict[str, Any] = {"error": message}
    if how_to_fix:
        payload["how_to_fix"] = how_to_fix
    payload.update({k: v for k, v in extra.items() if v is not None})
    return dumps(payload)


def describe_exception(exc: Exception, operation: str, site_url: Optional[str] = None) -> str:
    """Turn any exception into a helpful JSON error string."""
    if isinstance(exc, ToolError):
        return error_payload(exc.message, exc.how_to_fix, site_url=site_url)
    if isinstance(exc, auth.AuthError):
        return error_payload(
            str(exc),
            ["Call `get_capabilities` to see the auth status, or `setup_gsc_access` to fix it in-chat."],
        )

    status, message, reason = _http_details(exc)
    if status == 404 and site_url:
        return error_payload(f"Property '{site_url}' was not found (404) while {operation}.", _site_not_found_steps(site_url), site_url=site_url)
    if status == 403:
        steps = [
            "Make sure the signed-in Google account (or the service account email) is a user on this "
            "property: Search Console > Settings > Users and permissions > Add user.",
            "Check that site_url matches the property EXACTLY: 'https://example.com/' and "
            "'sc-domain:example.com' are different properties. Run `list_properties` to copy it.",
        ]
        if reason == "quotaExceeded" or "quota" in message.lower():
            steps = ["You hit a Google API quota. Wait a few minutes (URL Inspection: 600/min, 2,000/day per property) and retry."]
        if "indexing" in operation.lower():
            steps.insert(0, "The Indexing API needs OWNER permission on the property and the Indexing API enabled in your Google Cloud project.")
        if "insufficient" in message.lower() and "scope" in message.lower():
            steps.insert(0, "Your saved sign-in is missing a permission scope. Call `reauthenticate` to sign in again.")
        return error_payload(f"Permission denied while {operation}: {message}", steps, site_url=site_url)
    if status == 401:
        return error_payload(
            f"Google rejected the credentials while {operation}.",
            ["Call `reauthenticate` (OAuth) or create a fresh service account key and update GSC_CREDENTIALS_PATH."],
        )
    if status == 400:
        return error_payload(
            f"Google rejected the request while {operation}: {message}",
            [
                "Check dates are YYYY-MM-DD and within the last 16 months.",
                "Discover / Google News do not support the query dimension.",
                "searchAppearance can only be grouped alone (or with date).",
                "Call `list_filter_options` for valid operators and values.",
            ],
            site_url=site_url,
        )
    if status == 429:
        return error_payload(f"Rate limited by Google while {operation}.", ["Wait a minute and try again, or reduce batch size."])
    if status in (500, 502, 503, 504):
        return error_payload(f"Google Search Console API is temporarily unavailable ({status}) while {operation}.", ["Try again in a few minutes."])
    if status:
        return error_payload(f"HTTP {status} while {operation}: {message}", site_url=site_url)
    log.exception("Unexpected error while %s", operation)
    return error_payload(f"Error while {operation}: {exc.__class__.__name__}: {exc}", site_url=site_url)


def _http_details(exc: Exception) -> tuple[Optional[int], str, str]:
    try:
        from googleapiclient.errors import HttpError
    except Exception:  # pragma: no cover
        HttpError = ()  # type: ignore
    if HttpError and isinstance(exc, HttpError):
        status = getattr(getattr(exc, "resp", None), "status", None)
        message, reason = str(exc), ""
        try:
            content = json.loads(exc.content.decode("utf-8"))
            err = content.get("error", {})
            message = err.get("message", message)
            errs = err.get("errors") or [{}]
            reason = errs[0].get("reason", "")
        except Exception:
            pass
        return int(status) if status else None, message, reason
    text = str(exc)
    m = re.search(r"\b(4\d\d|5\d\d)\b", text)
    return (int(m.group(1)) if m and "HttpError" in exc.__class__.__name__ else None), text, ""


def _site_not_found_steps(site_url: str) -> list[str]:
    steps = ["Run `list_properties` and copy the property string exactly."]
    if site_url.startswith("sc-domain:"):
        steps.append(
            "Domain properties need the account/service account added under Settings > Users and "
            "permissions on that exact domain property."
        )
    else:
        steps.append("If you verified the whole domain, use 'sc-domain:example.com' instead of a URL.")
        steps.append("URL-prefix properties need the exact protocol, www and trailing slash, e.g. 'https://www.example.com/'.")
    steps.append("Make sure the authenticated account has access to the property.")
    return steps


# --------------------------------------------------------------------------- execution

def execute(request) -> Any:
    """Execute a googleapiclient request with automatic retry on 429/5xx."""
    return request.execute(num_retries=cfg.SETTINGS.api_retries)


def service(api: str = "searchconsole", version: str = "v1"):
    return auth.build_service(api, version)


# --------------------------------------------------------------------------- sites

_SITE_CACHE: dict[str, Any] = {"at": 0.0, "sites": None}
_SITE_LOCK = threading.Lock()


def list_sites_cached(force: bool = False) -> list[dict[str, str]]:
    with _SITE_LOCK:
        fresh = time.time() - _SITE_CACHE["at"] < 600
        if _SITE_CACHE["sites"] is not None and fresh and not force:
            return _SITE_CACHE["sites"]
    resp = execute(service().sites().list())
    sites = [
        {"site_url": s.get("siteUrl", ""), "permission_level": s.get("permissionLevel", "")}
        for s in resp.get("siteEntry", [])
    ]
    with _SITE_LOCK:
        _SITE_CACHE.update(at=time.time(), sites=sites)
    return sites


def clear_site_cache() -> None:
    with _SITE_LOCK:
        _SITE_CACHE.update(at=0.0, sites=None)


def _candidates(raw: str) -> list[str]:
    s = raw.strip()
    if s.startswith("sc-domain:"):
        return [s, "sc-domain:" + s[len("sc-domain:"):].strip().lower()]
    out = [s]
    if s.startswith(("http://", "https://")):
        if not s.endswith("/"):
            out.append(s + "/")
        host = re.sub(r"^https?://", "", s).split("/")[0].lower()
    else:
        host = s.split("/")[0].lower()
    bare = host[4:] if host.startswith("www.") else host
    if bare:
        out += [
            f"sc-domain:{bare}",
            f"https://{bare}/",
            f"https://www.{bare}/",
            f"http://{bare}/",
            f"http://www.{bare}/",
        ]
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def resolve_site(site_url: Optional[str]) -> str:
    """Return a property string the API will accept.

    Falls back to GSC_SITE_URL, and turns 'example.com' or a URL without a
    trailing slash into the matching property from list_properties.
    """
    raw = (site_url or "").strip() or (cfg.SETTINGS.site_url or "").strip()
    if not raw:
        raise ToolError(
            "No site_url given and no default property is set.",
            [
                "Pass site_url (run `list_properties` to see exact values), or",
                "set GSC_SITE_URL in the server env, or call `setup_gsc_access` with site_url.",
            ],
        )
    try:
        known = {s["site_url"] for s in list_sites_cached()}
    except Exception:
        return raw  # let the real call surface the auth/API error
    if raw in known:
        return raw
    for cand in _candidates(raw):
        if cand in known:
            return cand
    return raw


# --------------------------------------------------------------------------- params

def parse_list(value: Any) -> list[str]:
    """Accept a list, a JSON array string, or comma/newline separated text."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(v).strip() for v in data if str(v).strip()]
        except json.JSONDecodeError:
            pass
    parts = re.split(r"[\n,]+", text)
    return [p.strip() for p in parts if p.strip()]


def parse_urls(value: Any) -> list[str]:
    """Like parse_list but only splits on newlines/commas/whitespace between URLs."""
    if isinstance(value, (list, tuple)):
        items = [str(v).strip() for v in value]
    else:
        text = str(value or "").strip()
        if text.startswith("["):
            return parse_list(text)
        items = re.split(r"[\s,]+", text)
    return [i for i in items if i]


def normalize_dimensions(value: Any, default: str = "query") -> list[str]:
    dims = parse_list(value) or [default]
    out: list[str] = []
    for d in dims:
        canon = VALID_DIMENSIONS.get(d.strip().lower().replace(" ", ""))
        if canon is None:
            canon = VALID_DIMENSIONS.get(d.strip().lower())
        if canon is None:
            raise ToolError(
                f"Invalid dimension '{d}'.",
                [f"Valid dimensions: {', '.join(sorted(set(VALID_DIMENSIONS.values())))}."],
            )
        if canon not in out:
            out.append(canon)
    return out


def normalize_search_type(value: Optional[str]) -> str:
    key = str(value or "web").strip().lower()
    canon = SEARCH_TYPE_MAP.get(key)
    if not canon:
        raise ToolError(f"Invalid search_type '{value}'.", ["Use one of: web, image, video, news, discover, googleNews."])
    return canon


def normalize_filters(filters: Any = None, dimension: Optional[str] = None, operator: Optional[str] = None, expression: Optional[str] = None) -> list[dict[str, str]]:
    raw: list[dict[str, Any]] = []
    if filters not in (None, "", []):
        if isinstance(filters, str):
            try:
                filters = json.loads(filters)
            except json.JSONDecodeError:
                raise ToolError("filters must be a JSON array, e.g. [{\"dimension\":\"device\",\"operator\":\"equals\",\"expression\":\"MOBILE\"}].")
        if isinstance(filters, dict):
            filters = [filters]
        if not isinstance(filters, list):
            raise ToolError("filters must be a list of {dimension, operator, expression} objects.")
        raw = list(filters)
    elif dimension and expression not in (None, ""):
        raw = [{"dimension": dimension, "operator": operator or "contains", "expression": expression}]

    out = []
    for f in raw:
        if not isinstance(f, dict) or "dimension" not in f or "expression" not in f:
            raise ToolError(f"Each filter needs 'dimension' and 'expression' (and optionally 'operator'). Got: {f}")
        dim = VALID_DIMENSIONS.get(str(f["dimension"]).strip().lower())
        if dim not in FILTERABLE_DIMENSIONS:
            raise ToolError(f"Cannot filter on '{f['dimension']}'.", [f"Filterable: {', '.join(sorted(FILTERABLE_DIMENSIONS))}."])
        op = OPERATOR_MAP.get(str(f.get("operator", "equals")).strip().lower().replace(" ", ""))
        if not op:
            raise ToolError(f"Invalid operator '{f.get('operator')}'.", ["Use equals, notEquals, contains, notContains, includingRegex or excludingRegex."])
        expr = str(f["expression"])
        if dim == "device":
            expr = expr.upper()
        if dim == "country" and op in ("equals", "notEquals"):
            expr = expr.lower()
        out.append({"dimension": dim, "operator": op, "expression": expr})
    return out


def resolve_data_state(value: Optional[str]) -> str:
    state = str(value or cfg.SETTINGS.data_state).strip().lower()
    if state not in ("all", "final"):
        raise ToolError(f"Invalid data_state '{value}'.", ["Use 'all' (matches dashboard) or 'final' (confirmed data, 2-3 day lag)."])
    return state


def _parse_date(value: str, field: str) -> date:
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ToolError(f"{field} must be YYYY-MM-DD, got '{value}'.")


def date_range(days: Any = 28, start_date: Optional[str] = None, end_date: Optional[str] = None, data_state: str = "all") -> tuple[str, str, int]:
    """Return (start, end, day_count). Explicit dates win over `days`."""
    today = date.today()
    lag = 1 if data_state == "all" else 3
    end = _parse_date(end_date, "end_date") if end_date else today - timedelta(days=lag)
    if start_date:
        start = _parse_date(start_date, "start_date")
    else:
        n = coerce_int(days, 28, 1, 500)
        start = end - timedelta(days=n - 1)
    if start > end:
        raise ToolError(f"start_date {start} is after end_date {end}.")
    return start.isoformat(), end.isoformat(), (end - start).days + 1


def previous_range(start: str, end: str) -> tuple[str, str]:
    s = _parse_date(start, "start")
    e = _parse_date(end, "end")
    length = (e - s).days + 1
    pe = s - timedelta(days=1)
    ps = pe - timedelta(days=length - 1)
    return ps.isoformat(), pe.isoformat()


def coerce_int(val: Any, default: int, lo: Optional[int] = None, hi: Optional[int] = None) -> int:
    try:
        if val is None or val == "":
            res = default
        elif isinstance(val, bool):
            res = int(val)
        elif isinstance(val, (int, float)):
            res = int(val)
        else:
            res = int(float(str(val).strip().replace(",", "")))
    except (TypeError, ValueError):
        res = default
    if lo is not None:
        res = max(lo, res)
    if hi is not None:
        res = min(hi, res)
    return res


def coerce_float(val: Any, default: float) -> float:
    try:
        return float(str(val).strip().rstrip("%")) if val not in (None, "") else default
    except (TypeError, ValueError):
        return default


def coerce_bool(val: Any, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    s = str(val).strip().lower()
    if s in ("true", "1", "yes", "y", "t", "on"):
        return True
    if s in ("false", "0", "no", "n", "f", "off"):
        return False
    return default


# --------------------------------------------------------------------------- analytics

def build_query(
    start: str,
    end: str,
    dimensions: list[str],
    *,
    search_type: str = "web",
    filters: Optional[list[dict]] = None,
    row_limit: int = 1000,
    start_row: int = 0,
    data_state: str = "all",
    aggregation_type: Optional[str] = None,
) -> dict[str, Any]:
    api_dims = ["HOUR" if d == "hour" else d for d in dimensions]
    body: dict[str, Any] = {
        "startDate": start,
        "endDate": end,
        "dimensions": api_dims,
        "type": search_type,
        "rowLimit": max(1, min(int(row_limit), 25000)),
        "startRow": max(0, int(start_row)),
        "dataState": "HOURLY_ALL" if "hour" in dimensions else data_state,
    }
    if not api_dims:
        body.pop("dimensions")
    if filters:
        body["dimensionFilterGroups"] = [{"groupType": "and", "filters": filters}]
    if aggregation_type:
        body["aggregationType"] = aggregation_type
    return body


def run_query(site_url: str, body: dict[str, Any]) -> list[dict]:
    resp = execute(service().searchanalytics().query(siteUrl=site_url, body=body))
    return resp.get("rows", []) or []


def fetch_all_rows(site_url: str, body: dict[str, Any], max_rows: int = 25000) -> list[dict]:
    """Page through results 25,000 rows at a time up to max_rows."""
    rows: list[dict] = []
    start = body.get("startRow", 0)
    page_size = 25000
    while len(rows) < max_rows:
        page_body = dict(body, startRow=start, rowLimit=min(page_size, max_rows - len(rows)))
        page = run_query(site_url, page_body)
        rows.extend(page)
        if len(page) < page_body["rowLimit"]:
            break
        start += len(page)
    return rows


def format_row(row: dict, dimensions: list[str]) -> dict[str, Any]:
    keys = row.get("keys", []) or []
    out: dict[str, Any] = {}
    for i, dim in enumerate(dimensions):
        out[dim] = keys[i] if i < len(keys) else None
    out["clicks"] = int(row.get("clicks", 0) or 0)
    out["impressions"] = int(row.get("impressions", 0) or 0)
    out["ctr"] = round(float(row.get("ctr", 0) or 0) * 100, 2)
    out["position"] = round(float(row.get("position", 0) or 0), 1)
    return out


def totals(rows: Iterable[dict]) -> dict[str, Any]:
    """Aggregate formatted or raw rows (impression-weighted position)."""
    clicks = imps = 0
    weighted = 0.0
    n = 0
    for r in rows:
        c = int(r.get("clicks", 0) or 0)
        i = int(r.get("impressions", 0) or 0)
        clicks += c
        imps += i
        weighted += float(r.get("position", 0) or 0) * i
        n += 1
    return {
        "clicks": clicks,
        "impressions": imps,
        "ctr": round(clicks / imps * 100, 2) if imps else 0.0,
        "position": round(weighted / imps, 1) if imps else 0.0,
        "rows": n,
    }


def pct_change(new: float, old: float) -> Optional[float]:
    if not old:
        return None
    return round((new - old) / old * 100, 1)


def sort_rows(rows: list[dict], sort_by: str = "clicks", direction: str = "descending") -> list[dict]:
    if sort_by in ("clicks", "impressions", "ctr", "position"):
        reverse = str(direction).lower() not in ("ascending", "asc")
        rows.sort(key=lambda r: r.get(sort_by, 0), reverse=reverse)
    return rows


def fmt_time(raw: Optional[str], with_time: bool = True) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")
    except Exception:
        return raw
