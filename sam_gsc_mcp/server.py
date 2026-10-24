"""Sam GSC MCP — the all-in-one Google Search Console MCP server for SEOs. See README.md."""

# NOTE: no `from __future__ import annotations` here — the MCP SDK inspects
# real annotation objects to find the injected Context parameter.
import asyncio
import csv
import json
import logging
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Callable, Optional, Union

from pydantic import BaseModel, Field

from . import __version__, auth
from . import config as cfg
from . import gsc, inspection, reference, skills
from .compat import SDK_MAJOR, Context, annotations, make_server, try_elicit
from .gsc import ToolError, describe_exception, dumps, error_payload

logging.basicConfig(
    level=os.environ.get("GSC_LOG_LEVEL", "WARNING").upper(),
    format="%(asctime)s [sam-gsc-mcp] %(levelname)s %(message)s",
    stream=sys.stderr,
)
# Some MCP hosts treat any stderr noise as a crash; silence the chatty client cache warning.
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.ERROR)
log = logging.getLogger("sam_gsc_mcp")

REPO = "krishanthsam/sam-gsc-mcp"
REPO_URL = f"https://github.com/{REPO}"

INSTRUCTIONS = """\
Sam GSC MCP gives you live Google Search Console data.

How to work with this server:
1. Start with list_properties to get the exact site_url (or rely on the default property if one is set). 'example.com' is auto-matched to the right property.
2. For anything beyond a raw pull, call skills_list and skill_read — the playbooks hold proven field combinations and how to read the results.
3. Use list_available_dimensions / list_filter_options instead of guessing names.
4. If a tool reports an auth or setup error, call get_capabilities, then setup_gsc_access or reauthenticate.

Data quirks: ctr is returned as a PERCENTAGE; position is an average where LOWER is better; data lags 1-3 days; Google keeps 16 months of data; hourly data covers about the last 10 days.
"""

mcp = make_server("Sam GSC MCP", __version__, INSTRUCTIONS, REPO_URL)

# --------------------------------------------------------------------------- registry

TOOL_REGISTRY: list[dict[str, Any]] = []
CATEGORY_LABELS = {
    "setup": "Setup & server",
    "reference": "Reference (schema)",
    "skills": "SEO skills (playbooks)",
    "properties": "Properties",
    "analytics": "Search analytics & reporting",
    "insights": "SEO insights",
    "inspection": "URL inspection & indexing status",
    "indexing": "Indexing API (opt-in)",
    "sitemaps": "Sitemaps",
}


def _enabled(name: str, toolset: str, writes: bool, requires: Optional[str]) -> tuple[bool, Optional[str]]:
    s = cfg.SETTINGS
    if toolset not in s.toolsets:
        return False, f"toolset '{toolset}' not in GSC_TOOLSETS"
    if name in s.disabled_tools:
        return False, "listed in GSC_DISABLED_TOOLS"
    if writes and s.read_only:
        return False, "GSC_READ_ONLY=true"
    if requires == "indexing" and not s.enable_indexing_api:
        return False, "set GSC_ENABLE_INDEXING_API=true"
    if requires == "aliases" and not s.compat_aliases:
        return False, "set GSC_COMPAT_ALIASES=true"
    return True, None


def tool(
    toolset: str,
    title: str,
    *,
    read_only: bool = True,
    destructive: bool = False,
    idempotent: bool = True,
    open_world: bool = True,
    requires: Optional[str] = None,
    name: Optional[str] = None,
):
    """Register a tool with category metadata, honouring GSC_TOOLSETS etc."""

    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        enabled, reason = _enabled(tool_name, toolset, not read_only, requires)
        summary = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
        TOOL_REGISTRY.append(
            {
                "name": tool_name,
                "toolset": toolset,
                "title": title,
                "summary": summary,
                "enabled": enabled,
                "disabled_reason": reason,
                "writes": not read_only,
                "destructive": destructive,
                "alias": requires == "aliases",
            }
        )
        if enabled:
            mcp.tool(
                name=tool_name,
                annotations=annotations(
                    title=title,
                    read_only=read_only,
                    destructive=destructive,
                    idempotent=idempotent,
                    open_world=open_world,
                ),
            )(fn)
        return fn

    return decorator


async def _call(operation: str, fn: Callable[..., Any], *args: Any, site_url: Optional[str] = None, **kwargs: Any) -> str:
    """Run blocking Google API work in a worker thread and convert errors to JSON."""
    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
        return result if isinstance(result, str) else dumps(result)
    except Exception as exc:
        return describe_exception(exc, operation, site_url)


def _destructive_blocked(tool_name: str) -> Optional[str]:
    if cfg.SETTINGS.allow_destructive:
        return None
    return error_payload(
        f"Safety: {tool_name} changes or removes data in your Search Console account and is disabled by default.",
        ["Set GSC_ALLOW_DESTRUCTIVE=true in this server's env config and restart your AI client to enable it."],
    )


DimArg = Union[str, list[str]]
FilterArg = Union[str, list[dict[str, Any]], dict[str, Any], None]


# =========================================================================== SETUP

def _auth_status() -> dict[str, Any]:
    try:
        auth.get_credentials(allow_browser=False)
        method = auth.current_method()
        status: dict[str, Any] = {"authenticated": True, "method": method}
        if method == "service_account":
            status["service_account_email"] = auth.service_account_email()
        return status
    except Exception as exc:
        return {"authenticated": False, "detail": str(exc)}


@tool("setup", "Capabilities & auth status", open_world=False)
async def get_capabilities() -> str:
    """List every tool by category, the current auth status and active settings. Call this FIRST when unsure what the server can do or when something fails.
    """

    def work():
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for t in TOOL_REGISTRY:
            entry = {"name": t["name"], "summary": t["summary"]}
            if not t["enabled"]:
                entry["disabled"] = t["disabled_reason"]
            if t["destructive"]:
                entry["destructive"] = True
            grouped[CATEGORY_LABELS.get(t["toolset"], t["toolset"])].append(entry)
        enabled_count = sum(1 for t in TOOL_REGISTRY if t["enabled"])
        return {
            "server": "Sam GSC MCP",
            "version": __version__,
            "mcp_sdk_major": SDK_MAJOR,
            "auth": _auth_status(),
            "settings": cfg.SETTINGS.describe(),
            "tools_enabled": enabled_count,
            "tools": grouped,
            "skills": [s["id"] for s in skills.list_skills()],
            "getting_started": [
                "Not authenticated? OAuth users: call `reauthenticate` to open the Google sign-in page. "
                "Service account users: check GSC_CREDENTIALS_PATH. Or call `setup_gsc_access`.",
                "Call `list_properties` to get exact site_url values (or set GSC_SITE_URL as a default).",
                "Call `skills_list` for ready-made SEO workflows (weekly report, cannibalization, indexing audit...).",
            ],
        }

    return await _call("reading capabilities", work)


class _SetupChoice(BaseModel):
    auth_method: str = Field(description="Type 'oauth' (sign in with your Google account) or 'service_account' (JSON key)")
    file_path: str = Field(description="ABSOLUTE path to the OAuth client JSON (oauth) or the service account JSON key")
    site_url: str = Field(default="", description="Optional default property, e.g. 'sc-domain:example.com' or 'https://www.example.com/'")


@tool("setup", "Set up / fix GSC access", read_only=False, idempotent=True)
async def setup_gsc_access(
    auth_method: Optional[str] = None,
    credentials_path: Optional[str] = None,
    oauth_client_secrets_file: Optional[str] = None,
    site_url: Optional[str] = None,
    save: bool = True,
    ctx: Context = None,
) -> str:
    """Configure or repair Google Search Console access in-chat, without editing config files or restarting.

    Pass the values directly, or call with no arguments and the server will ask you for them
    (when your client supports interactive prompts). Only file PATHS are stored — never key contents.

    Args:
        auth_method: 'oauth' or 'service_account' (auto-detected from the file if omitted)
        credentials_path: Absolute path to a service account JSON key
        oauth_client_secrets_file: Absolute path to an OAuth 'Desktop app' client JSON
        site_url: Optional default property used when tools are called without site_url
        save: Save these paths to the server's config.json so they survive restarts (default true)
    """
    if not any([auth_method, credentials_path, oauth_client_secrets_file, site_url]):
        status = await asyncio.to_thread(_auth_status)
        if status.get("authenticated"):
            try:
                sites = await asyncio.to_thread(gsc.list_sites_cached, True)
            except Exception as exc:
                return describe_exception(exc, "verifying access")
            return dumps(
                {
                    "status": "already_configured",
                    "auth": status,
                    "properties": sites,
                    "default_site_url": cfg.SETTINGS.site_url,
                    "tip": "Pass site_url to set a default property, or call reauthenticate to switch Google accounts.",
                }
            )
        action, data = await try_elicit(
            ctx,
            "Let's connect Google Search Console. Choose 'oauth' to sign in with your Google account "
            "(needs an OAuth 'Desktop app' client JSON) or 'service_account' (needs a JSON key whose email "
            "is added as a user in Search Console). Paste the ABSOLUTE path to the JSON file.",
            _SetupChoice,
        )
        if action == "unsupported":
            return error_payload(
                "Not authenticated yet, and this client can't show interactive setup prompts.",
                [
                    "Call setup_gsc_access again with oauth_client_secrets_file='/absolute/path/client_secrets.json' "
                    "or credentials_path='/absolute/path/service_account.json' (and optionally site_url).",
                    "Or set GSC_OAUTH_CLIENT_SECRETS_FILE / GSC_CREDENTIALS_PATH in the server env and restart.",
                ],
                auth=status,
            )
        if action != "accept" or data is None:
            return dumps({"status": "cancelled", "message": "Setup cancelled — nothing was changed."})
        auth_method = (data.auth_method or "").strip().lower()
        if "service" in auth_method:
            credentials_path = data.file_path
        else:
            oauth_client_secrets_file = data.file_path
        site_url = data.site_url or None

    def work():
        updates: dict[str, Any] = {}
        notes: list[str] = []
        for label, raw in (("credentials_path", credentials_path), ("oauth_client_secrets_file", oauth_client_secrets_file)):
            path = cfg.expand_path(raw)
            if not path:
                continue
            kind, detail = auth.inspect_credentials_file(path)
            if kind == "missing":
                raise ToolError(f"File not found: {path}", ["Use the ABSOLUTE path on the machine running this server."])
            if kind == "invalid":
                raise ToolError(f"{path} is not a Google credentials file ({detail}).")
            if kind == "service_account":
                updates["credentials_path"] = path
                updates["auth_mode"] = "service_account"
                notes.append(f"Service account detected: {detail}. Make sure it is added as a user in Search Console.")
            elif kind == "oauth_client":
                updates["oauth_client_secrets_file"] = path
                updates["auth_mode"] = "oauth"
                notes.append("OAuth client detected. A Google sign-in page will open in your browser if needed.")
            else:
                raise ToolError(f"{path} looks like a saved user token, not a client or key file.")
        if auth_method and "auth_mode" not in updates:
            mode = auth_method.strip().lower().replace("-", "_")
            updates["auth_mode"] = "service_account" if "service" in mode else ("adc" if mode == "adc" else "oauth")
        if site_url:
            updates["site_url"] = site_url.strip()

        # Apply for this session (env wins over config.json, so set env too).
        env_map = {
            "credentials_path": "GSC_CREDENTIALS_PATH",
            "oauth_client_secrets_file": "GSC_OAUTH_CLIENT_SECRETS_FILE",
            "site_url": "GSC_SITE_URL",
            "auth_mode": "GSC_AUTH_MODE",
        }
        for key, env in env_map.items():
            if key in updates:
                os.environ[env] = str(updates[key])
        if updates.get("auth_mode") in ("oauth", "service_account"):
            os.environ.pop("GSC_SKIP_OAUTH", None)
        cfg.reload_settings()
        auth.reset_cache()
        gsc.clear_site_cache()

        sites = gsc.list_sites_cached(force=True)  # verifies the credentials for real
        saved_to = None
        if save and updates:  # only persist settings that were proven to work
            saved_to = str(cfg.save_settings(updates, cfg.SETTINGS))
        result: dict[str, Any] = {
            "status": "connected",
            "auth": {"method": auth.current_method()},
            "properties": sites,
            "default_site_url": cfg.SETTINGS.site_url,
            "notes": notes,
            "saved_to": saved_to,
        }
        if cfg.SETTINGS.site_url and cfg.SETTINGS.site_url not in {s["site_url"] for s in sites}:
            result["warning"] = (
                f"Default property '{cfg.SETTINGS.site_url}' is not in the accessible list; it will be auto-matched "
                "if possible, otherwise pick one of the properties above."
            )
        if not sites:
            result["warning"] = (
                "Signed in, but this account has no Search Console properties. For a service account, add its "
                "email under Search Console > Settings > Users and permissions."
            )
        return result

    return await _call("setting up GSC access", work)


@tool("setup", "Re-authenticate (OAuth)", read_only=False, idempotent=False)
async def reauthenticate() -> str:
    """Sign out and open the Google sign-in page again — use it to log in the first time, fix expired tokens or switch Google accounts (OAuth only)."""

    def work():
        removed = auth.logout()
        gsc.clear_site_cache()
        secrets = next((p for p in cfg.SETTINGS.possible_client_secret_paths() if p and os.path.isfile(p)), None)
        if not secrets:
            raise ToolError(
                "No OAuth client secrets file found, so a sign-in window can't be opened.",
                [
                    "Set GSC_OAUTH_CLIENT_SECRETS_FILE to the ABSOLUTE path of your 'Desktop app' OAuth client JSON, "
                    "or call setup_gsc_access with oauth_client_secrets_file.",
                    "Using a service account instead? You don't need this tool — check GSC_CREDENTIALS_PATH.",
                ],
            )
        auth.run_oauth_flow(secrets)
        auth.reset_cache()
        sites = gsc.list_sites_cached(force=True)
        return {
            "status": "authenticated",
            "previous_session_removed": removed,
            "token_file": str(cfg.SETTINGS.token_file),
            "properties": sites,
        }

    return await _call("re-authenticating", work)


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


@tool("setup", "Check for updates", open_world=True)
async def check_for_updates() -> str:
    """Check GitHub for a newer version of Sam GSC MCP and show the upgrade command."""

    def work():
        if not cfg.SETTINGS.update_check:
            return {"current_version": __version__, "message": "Update checks are disabled (GSC_UPDATE_CHECK=false)."}
        latest = None
        source = None
        headers = {"User-Agent": inspection.USER_AGENT, "Accept": "application/vnd.github+json"}
        try:
            req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:  # noqa: S310
                latest = json.loads(resp.read().decode()).get("tag_name", "").lstrip("v")
                source = "GitHub release"
        except Exception:
            try:
                req = urllib.request.Request(f"https://raw.githubusercontent.com/{REPO}/main/pyproject.toml", headers=headers)
                with urllib.request.urlopen(req, timeout=6) as resp:  # noqa: S310
                    m = re.search(r'^version\s*=\s*"([^"]+)"', resp.read().decode(), re.M)
                    latest = m.group(1) if m else None
                    source = "pyproject.toml on main"
            except Exception as exc:
                return {"current_version": __version__, "error": f"Could not reach GitHub: {exc}"}
        if not latest:
            return {"current_version": __version__, "message": "No published version found."}
        newer = _version_tuple(latest) > _version_tuple(__version__)
        return {
            "current_version": __version__,
            "latest_version": latest,
            "source": source,
            "update_available": newer,
            "how_to_update": [
                f"uvx: uvx --refresh --from git+{REPO_URL} sam-gsc-mcp  (then restart your AI client)",
                "git clone: git pull && uv pip install -e .",
            ]
            if newer
            else [],
            "changelog": f"{REPO_URL}/blob/main/CHANGELOG.md",
        }

    return await _call("checking for updates", work)


@tool("setup", "About the creator", open_world=False)
async def get_creator_info() -> str:
    """About Krishanth Sam, who built Sam GSC MCP."""
    return dumps(
        {
            "creator": "Krishanth Sam",
            "website": "https://example.com",
            "linkedin": "https://www.linkedin.com/in/krishanth-sam",
            "github": "https://github.com/krishanthsam",
            "project": REPO_URL,
        }
    )


# =========================================================================== REFERENCE

@tool("reference", "List dimensions", open_world=False)
async def list_available_dimensions() -> str:
    """List every Search Analytics dimension (query, page, country, device, date, searchAppearance, hour) with what it means."""
    return dumps({"dimensions": reference.DIMENSIONS})


@tool("reference", "List metrics", open_world=False)
async def list_available_metrics() -> str:
    """List the four Search Analytics metrics (clicks, impressions, ctr, position) and their units."""
    return dumps({"metrics": reference.METRICS})


@tool("reference", "List filter options", open_world=False)
async def list_filter_options() -> str:
    """Valid filter operators, search types, device values, common search appearances, data states and example filters."""
    return dumps(
        {
            "operators": reference.OPERATORS,
            "search_types": reference.SEARCH_TYPES,
            "device_values": reference.DEVICE_VALUES,
            "common_search_appearances": reference.COMMON_SEARCH_APPEARANCES,
            "data_states": reference.DATA_STATES,
            "filter_examples": reference.FILTER_EXAMPLES,
            "notes": [
                "Multiple filters are combined with AND.",
                "Country codes are lowercase ISO alpha-3 (ind, usa, gbr).",
                "Regex uses RE2 syntax; prefix (?i) for case-insensitive.",
            ],
        }
    )


# =========================================================================== SKILLS

@tool("skills", "List SEO skills", open_world=False)
async def skills_list() -> str:
    """List the bundled SEO playbooks (weekly report, cannibalization, indexing audit, content opportunities, brand visibility, traffic-drop diagnosis and more). Read one with skill_read."""
    items = skills.list_skills()
    if not items:
        return error_payload("No skills folder found next to the server.")
    return dumps({"count": len(items), "skills": items})


@tool("skills", "Read an SEO skill", open_world=False)
async def skill_read(skill_id: str) -> str:
    """Return the full step-by-step playbook for one skill.

    Args:
        skill_id: Skill id from skills_list, e.g. "seo-weekly-report" or "keyword-cannibalization"
    """
    data = skills.read_skill(skill_id)
    if not data:
        return error_payload(f"Skill '{skill_id}' not found.", ["Call skills_list to see available ids."])
    return dumps(data)


# =========================================================================== PROPERTIES

@tool("properties", "List properties")
async def list_properties() -> str:
    """List all Google Search Console properties (sites) you can access, with permission level. Call this first to get the exact site_url for other tools."""

    def work():
        sites = gsc.list_sites_cached(force=True)
        if not sites:
            return {
                "count": 0,
                "properties": [],
                "hint": "No properties visible. For a service account, add its email as a user in Search Console > Settings > Users and permissions.",
            }
        return {"count": len(sites), "default_site_url": cfg.SETTINGS.site_url, "properties": sites}

    return await _call("listing properties", work)


@tool("properties", "Property details")
async def get_site_details(site_url: Optional[str] = None) -> str:
    """Permission level and verification/ownership details for one property.

    Args:
        site_url: Exact property from list_properties ("https://example.com/" or "sc-domain:example.com"). Defaults to GSC_SITE_URL.
    """

    def work():
        site = gsc.resolve_site(site_url)
        info = gsc.execute(gsc.service().sites().get(siteUrl=site))
        out: dict[str, Any] = {
            "site_url": site,
            "property_type": "domain" if site.startswith("sc-domain:") else "url-prefix",
            "permission_level": info.get("permissionLevel", "Unknown"),
        }
        if "siteVerificationInfo" in info:
            v = info["siteVerificationInfo"]
            out["verification"] = {"state": v.get("verificationState"), "verified_user": v.get("verifiedUser"), "method": v.get("verificationMethod")}
        if "ownershipInfo" in info:
            o = info["ownershipInfo"]
            out["ownership"] = {"owner": o.get("owner"), "verification_method": o.get("verificationMethod")}
        return out

    return await _call("reading site details", work, site_url=site_url)


@tool("properties", "Add a property", read_only=False, destructive=True)
async def add_site(site_url: str) -> str:
    """Add a property to your Search Console account (requires GSC_ALLOW_DESTRUCTIVE=true). You still need to verify ownership in Search Console.

    Args:
        site_url: e.g. "https://www.example.com/" (URL-prefix) or "sc-domain:example.com" (domain)
    """
    blocked = _destructive_blocked("add_site")
    if blocked:
        return blocked

    def work():
        try:
            gsc.execute(gsc.service().sites().add(siteUrl=site_url))
        except Exception as exc:
            if gsc._http_details(exc)[0] == 409:
                return {"status": "already_exists", "site_url": site_url}
            raise
        gsc.clear_site_cache()
        return {"status": "added", "site_url": site_url, "next_step": "Verify ownership in Search Console to see data."}

    return await _call("adding a site", work, site_url=site_url)


@tool("properties", "Remove a property", read_only=False, destructive=True)
async def delete_site(site_url: str) -> str:
    """Remove a property from your Search Console account (requires GSC_ALLOW_DESTRUCTIVE=true).

    Args:
        site_url: Exact property string from list_properties
    """
    blocked = _destructive_blocked("delete_site")
    if blocked:
        return blocked

    def work():
        gsc.execute(gsc.service().sites().delete(siteUrl=site_url))
        gsc.clear_site_cache()
        return {"status": "removed", "site_url": site_url}

    return await _call("removing a site", work, site_url=site_url)


# =========================================================================== ANALYTICS

def _analytics(
    site_url, dimensions, days, start_date, end_date, search_type, filters, row_limit, start_row,
    data_state, sort_by="clicks", sort_direction="descending", summary_only=False, intent=None,
    filter_dimension=None, filter_operator=None, filter_expression=None,
) -> dict[str, Any]:
    site = gsc.resolve_site(site_url)
    dims = gsc.normalize_dimensions(dimensions)
    state = gsc.resolve_data_state(data_state)
    start, end, n_days = gsc.date_range(days, start_date, end_date, state)
    stype = gsc.normalize_search_type(search_type)
    flt = gsc.normalize_filters(filters, filter_dimension, filter_operator, filter_expression)
    limit = gsc.coerce_int(row_limit, 1000, 1, 25000)
    offset = gsc.coerce_int(start_row, 0, 0)

    if gsc.coerce_bool(summary_only):
        body = gsc.build_query(start, end, [], search_type=stype, filters=flt, row_limit=1, data_state=state)
        rows = gsc.run_query(site, body)
        t = gsc.totals(rows) if rows else {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
        t.pop("rows", None)
        return {"site_url": site, "date_range": {"start": start, "end": end, "days": n_days}, "search_type": stype,
                "filters_applied": flt, "summary": t, "ctr_unit": "percent", "intent": intent}

    body = gsc.build_query(start, end, dims, search_type=stype, filters=flt, row_limit=limit, start_row=offset, data_state=state)
    raw = gsc.run_query(site, body)
    rows = gsc.sort_rows([gsc.format_row(r, dims) for r in raw], sort_by, sort_direction)
    has_more = len(raw) == limit
    out: dict[str, Any] = {
        "site_url": site,
        "date_range": {"start": start, "end": end, "days": n_days},
        "search_type": stype,
        "dimensions": dims,
        "data_state": body["dataState"],
        "filters_applied": flt,
        "ctr_unit": "percent",
        "pagination": {"start_row": offset, "row_count": len(rows), "has_more": has_more,
                       "next_start_row": offset + limit if has_more else None},
        "rows": rows,
    }
    if intent:
        out["intent"] = intent
    if not rows:
        out["message"] = "No data for these parameters. Try a longer date range, fewer filters, or another search_type."
    return out


@tool("analytics", "Search analytics")
async def get_search_analytics(
    site_url: Optional[str] = None,
    days: int = 28,
    dimensions: DimArg = "query",
    row_limit: int = 20,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search_type: str = "web",
    filters: FilterArg = None,
    summary_only: bool = False,
    data_state: Optional[str] = None,
    intent: Optional[str] = None,
) -> str:
    """Top queries/pages/countries/devices/dates with clicks, impressions, CTR (%) and position.

    Args:
        site_url: Exact property from list_properties. Defaults to GSC_SITE_URL. "example.com" is auto-matched.
        days: Days to look back (default 28). Ignored when start_date is given.
        dimensions: "query", "page", "country", "device", "date", "searchAppearance", "hour" — comma list or array, e.g. "query,page"
        row_limit: Rows to return (default 20, up to 25000). Use get_advanced_search_analytics or export_search_analytics for big pulls.
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional, defaults to the latest available day)
        search_type: web, image, video, news, discover, googleNews
        filters: AND-combined list, e.g. [{"dimension":"country","operator":"equals","expression":"ind"}]
        summary_only: True returns only totals (cheapest call)
        data_state: "all" (matches dashboard, default) or "final" (confirmed data only)
        intent: Optional one-line note of what you're trying to learn (echoed back for context)
    """
    return await _call(
        "fetching search analytics", _analytics, site_url, dimensions, days, start_date, end_date,
        search_type, filters, row_limit, 0, data_state, "clicks", "descending", summary_only, intent,
        site_url=site_url,
    )


@tool("analytics", "Advanced search analytics")
async def get_advanced_search_analytics(
    site_url: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dimensions: DimArg = "query",
    search_type: str = "web",
    row_limit: int = 1000,
    start_row: int = 0,
    sort_by: str = "clicks",
    sort_direction: str = "descending",
    filter_dimension: Optional[str] = None,
    filter_operator: str = "contains",
    filter_expression: Optional[str] = None,
    filters: FilterArg = None,
    data_state: Optional[str] = None,
    days: int = 28,
) -> str:
    """Power query: up to 25,000 rows per call with pagination, sorting, regex and multi-filter AND logic.

    Args:
        site_url: Exact property from list_properties (defaults to GSC_SITE_URL)
        start_date: YYYY-MM-DD (defaults to `days` ago)
        end_date: YYYY-MM-DD (defaults to latest day)
        dimensions: comma list or array, e.g. "query,page,device"
        search_type: web, image, video, news, discover, googleNews
        row_limit: Max rows (1-25000, default 1000)
        start_row: Offset for pagination (use next_start_row from the previous page)
        sort_by: clicks, impressions, ctr or position (applied to returned rows)
        sort_direction: descending or ascending (ascending position = best rankings first)
        filter_dimension: Single filter dimension (query, page, country, device, searchAppearance)
        filter_operator: equals, notEquals, contains, notContains, includingRegex, excludingRegex
        filter_expression: Value for the single filter
        filters: JSON array of filters (AND). Overrides the single-filter args.
        data_state: "all" (default) or "final"
        days: Look-back window when start_date is omitted (default 28)
    """
    return await _call(
        "fetching advanced search analytics", _analytics, site_url, dimensions, days, start_date, end_date,
        search_type, filters, row_limit, start_row, data_state, sort_by, sort_direction, False, None,
        filter_dimension, filter_operator, filter_expression, site_url=site_url,
    )


@tool("analytics", "Performance overview")
async def get_performance_overview(site_url: Optional[str] = None, days: int = 28, search_type: str = "web") -> str:
    """Site totals (clicks, impressions, CTR, position) plus the day-by-day trend.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        days: Days to look back (default 28)
        search_type: web, image, video, news, discover, googleNews
    """

    def work():
        site = gsc.resolve_site(site_url)
        state = cfg.SETTINGS.data_state
        start, end, n = gsc.date_range(days, None, None, state)
        stype = gsc.normalize_search_type(search_type)
        total_rows = gsc.run_query(site, gsc.build_query(start, end, [], search_type=stype, row_limit=1, data_state=state))
        daily = gsc.run_query(site, gsc.build_query(start, end, ["date"], search_type=stype, row_limit=1000, data_state=state))
        if not total_rows and not daily:
            return {"site_url": site, "date_range": {"start": start, "end": end, "days": n}, "message": "No performance data in this period."}
        t = gsc.totals(total_rows)
        t.pop("rows", None)
        trend = sorted((gsc.format_row(r, ["date"]) for r in daily), key=lambda r: r["date"])
        best = max(trend, key=lambda r: r["clicks"]) if trend else None
        worst = min(trend, key=lambda r: r["clicks"]) if trend else None
        return {
            "site_url": site,
            "date_range": {"start": start, "end": end, "days": n},
            "search_type": stype,
            "ctr_unit": "percent",
            "totals": t,
            "avg_daily_clicks": round(t["clicks"] / max(1, len(trend)), 1),
            "best_day": best,
            "worst_day": worst,
            "daily_trend": trend,
        }

    return await _call("building the performance overview", work, site_url=site_url)


@tool("analytics", "Site summary vs previous period")
async def get_site_summary(site_url: Optional[str] = None, period_days: int = 28, search_type: str = "web") -> str:
    """Headline summary: this period vs the previous period of the same length, with % changes and daily data.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        period_days: Length of each period in days (default 28)
        search_type: web, image, video, news, discover, googleNews
    """

    def work():
        site = gsc.resolve_site(site_url)
        state = cfg.SETTINGS.data_state
        start, end, n = gsc.date_range(period_days, None, None, state)
        pstart, pend = gsc.previous_range(start, end)
        stype = gsc.normalize_search_type(search_type)
        cur = [gsc.format_row(r, ["date"]) for r in gsc.run_query(site, gsc.build_query(start, end, ["date"], search_type=stype, row_limit=1000, data_state=state))]
        prev = [gsc.format_row(r, ["date"]) for r in gsc.run_query(site, gsc.build_query(pstart, pend, ["date"], search_type=stype, row_limit=1000, data_state=state))]
        ct, pt = gsc.totals(cur), gsc.totals(prev)
        for t in (ct, pt):
            t.pop("rows", None)
        return {
            "site_url": site,
            "period": {"start": start, "end": end, "days": n},
            "previous_period": {"start": pstart, "end": pend},
            "ctr_unit": "percent",
            "totals": ct,
            "previous_totals": pt,
            "changes": {
                "clicks_pct": gsc.pct_change(ct["clicks"], pt["clicks"]),
                "impressions_pct": gsc.pct_change(ct["impressions"], pt["impressions"]),
                "ctr_points": round(ct["ctr"] - pt["ctr"], 2),
                "position_change": round(pt["position"] - ct["position"], 1),
                "note": "position_change > 0 means rankings improved (moved up).",
            },
            "daily_data": sorted(cur, key=lambda r: r["date"]),
        }

    return await _call("building the site summary", work, site_url=site_url)


@tool("analytics", "Compare two periods")
async def compare_search_periods(
    site_url: Optional[str] = None,
    period1_start: Optional[str] = None,
    period1_end: Optional[str] = None,
    period2_start: Optional[str] = None,
    period2_end: Optional[str] = None,
    dimensions: DimArg = "query",
    limit: int = 20,
    search_type: str = "web",
    filters: FilterArg = None,
) -> str:
    """Compare two date ranges item by item (queries, pages...). Period 1 = the period you analyse, Period 2 = the baseline.

    Positive deltas mean Period 1 did better (more clicks/impressions, higher CTR, better/lower position).
    With no dates it compares the last 28 days against the 28 days before.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        period1_start: Analysed period start YYYY-MM-DD
        period1_end: Analysed period end YYYY-MM-DD
        period2_start: Baseline start YYYY-MM-DD
        period2_end: Baseline end YYYY-MM-DD
        dimensions: Group by, e.g. "query" or "page" or "query,page"
        limit: Number of biggest movers to return (default 20)
        search_type: web, image, video, news, discover, googleNews
        filters: Optional AND filters applied to both periods
    """

    def work():
        site = gsc.resolve_site(site_url)
        dims = gsc.normalize_dimensions(dimensions)
        state = cfg.SETTINGS.data_state
        stype = gsc.normalize_search_type(search_type)
        flt = gsc.normalize_filters(filters)
        if period1_start and period1_end:
            p1s, p1e, _ = gsc.date_range(None, period1_start, period1_end, state)
        else:
            p1s, p1e, _ = gsc.date_range(28, None, None, state)
        if period2_start and period2_end:
            p2s, p2e, _ = gsc.date_range(None, period2_start, period2_end, state)
        else:
            p2s, p2e = gsc.previous_range(p1s, p1e)

        def pull(s, e):
            body = gsc.build_query(s, e, dims, search_type=stype, filters=flt, row_limit=5000, data_state=state)
            return {tuple(r.get("keys", [])): r for r in gsc.fetch_all_rows(site, body, max_rows=5000)}

        d1, d2 = pull(p1s, p1e), pull(p2s, p2e)
        if not d1 and not d2:
            return {"site_url": site, "message": "No data in either period."}
        zero = {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
        items = []
        for key in set(d1) | set(d2):
            a, b = d1.get(key, zero), d2.get(key, zero)
            item = {dim: key[i] if i < len(key) else None for i, dim in enumerate(dims)}
            item.update(
                {
                    "p1_clicks": int(a["clicks"]), "p2_clicks": int(b["clicks"]),
                    "click_diff": int(a["clicks"] - b["clicks"]), "click_pct": gsc.pct_change(a["clicks"], b["clicks"]),
                    "p1_impressions": int(a["impressions"]), "p2_impressions": int(b["impressions"]),
                    "imp_diff": int(a["impressions"] - b["impressions"]), "imp_pct": gsc.pct_change(a["impressions"], b["impressions"]),
                    "p1_ctr": round(a["ctr"] * 100, 2), "p2_ctr": round(b["ctr"] * 100, 2),
                    "ctr_diff": round((a["ctr"] - b["ctr"]) * 100, 2),
                    "p1_position": round(a["position"], 1) if key in d1 else None,
                    "p2_position": round(b["position"], 1) if key in d2 else None,
                    "position_diff": round(b["position"] - a["position"], 1) if key in d1 and key in d2 else None,
                    "status": "new" if key not in d2 else ("lost" if key not in d1 else "both"),
                }
            )
            items.append(item)
        items.sort(key=lambda x: abs(x["click_diff"]), reverse=True)
        n = gsc.coerce_int(limit, 20, 1, 1000)
        t1 = gsc.totals(d1.values())
        t2 = gsc.totals(d2.values())
        for t in (t1, t2):
            t.pop("rows", None)
        return {
            "site_url": site,
            "period1": {"start": p1s, "end": p1e, "totals": t1},
            "period2": {"start": p2s, "end": p2e, "totals": t2},
            "dimensions": dims,
            "ctr_unit": "percent",
            "total_items": len(items),
            "new_items": sum(1 for i in items if i["status"] == "new"),
            "lost_items": sum(1 for i in items if i["status"] == "lost"),
            "top_gainers": [i for i in items if i["click_diff"] > 0][: max(1, n // 2)],
            "top_losers": [i for i in items if i["click_diff"] < 0][: max(1, n // 2)],
            "biggest_movers": items[:n],
        }

    return await _call("comparing periods", work, site_url=site_url)


@tool("analytics", "Queries for one page")
async def get_search_by_page_query(site_url: Optional[str] = None, page_url: str = "", days: int = 28, row_limit: int = 20, search_type: str = "web") -> str:
    """Search queries that bring traffic to one specific page.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        page_url: Full URL of the page (exact match)
        days: Days to look back (default 28)
        row_limit: Rows to return (default 20, up to 25000)
        search_type: web, image, video, news
    """

    def work():
        if not page_url:
            raise ToolError("page_url is required.")
        site = gsc.resolve_site(site_url)
        state = cfg.SETTINGS.data_state
        start, end, n = gsc.date_range(days, None, None, state)
        flt = [{"dimension": "page", "operator": "equals", "expression": page_url}]
        body = gsc.build_query(start, end, ["query"], search_type=gsc.normalize_search_type(search_type), filters=flt,
                               row_limit=gsc.coerce_int(row_limit, 20, 1, 25000), data_state=state)
        rows = [gsc.format_row(r, ["query"]) for r in gsc.run_query(site, body)]
        page_total = gsc.run_query(site, gsc.build_query(start, end, [], filters=flt, row_limit=1, data_state=state))
        t = gsc.totals(page_total) if page_total else gsc.totals(rows)
        t.pop("rows", None)
        return {
            "site_url": site, "page_url": page_url,
            "date_range": {"start": start, "end": end, "days": n},
            "ctr_unit": "percent",
            "page_totals": t,
            "row_count": len(rows),
            "rows": rows,
            "message": None if rows else "No query data for this page. Check the URL is exact (protocol, www, trailing slash).",
        }

    return await _call("fetching queries for a page", work, site_url=site_url)


@tool("analytics", "Hourly performance")
async def get_hourly_performance(site_url: Optional[str] = None, days: int = 3, filters: FilterArg = None, search_type: str = "web") -> str:
    """Hour-by-hour clicks and impressions for roughly the last 10 days (great for launches, news spikes and outage checks). Hourly data can be partial.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        days: Days of hourly data, 1-10 (default 3)
        filters: Optional AND filters, e.g. a page or query filter
        search_type: web, image, video, news, discover, googleNews
    """

    def work():
        site = gsc.resolve_site(site_url)
        n = gsc.coerce_int(days, 3, 1, 10)
        end = date.today()
        start = end - timedelta(days=n - 1)
        body = gsc.build_query(start.isoformat(), end.isoformat(), ["hour"], search_type=gsc.normalize_search_type(search_type),
                               filters=gsc.normalize_filters(filters), row_limit=25000)
        rows = sorted((gsc.format_row(r, ["hour"]) for r in gsc.run_query(site, body)), key=lambda r: r["hour"] or "")
        by_hour_of_day: dict[str, dict[str, int]] = defaultdict(lambda: {"clicks": 0, "impressions": 0})
        for r in rows:
            m = re.search(r"T(\d{2})", r["hour"] or "")
            if m:
                by_hour_of_day[m.group(1)]["clicks"] += r["clicks"]
                by_hour_of_day[m.group(1)]["impressions"] += r["impressions"]
        peak = max(by_hour_of_day.items(), key=lambda kv: kv[1]["clicks"])[0] if by_hour_of_day else None
        return {
            "site_url": site,
            "date_range": {"start": start.isoformat(), "end": end.isoformat(), "days": n},
            "data_state": "HOURLY_ALL",
            "note": "Hourly data may be partial and is reported in Pacific Time.",
            "ctr_unit": "percent",
            "peak_hour_of_day": peak,
            "by_hour_of_day": dict(sorted(by_hour_of_day.items())),
            "rows": rows,
        }

    return await _call("fetching hourly data", work, site_url=site_url)


@tool("analytics", "Export to CSV", read_only=True, open_world=True)
async def export_search_analytics(
    site_url: Optional[str] = None,
    dimensions: DimArg = "query,page",
    days: int = 90,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search_type: str = "web",
    filters: FilterArg = None,
    max_rows: int = 100000,
    file_name: Optional[str] = None,
) -> str:
    """Bulk-export Search Analytics rows (auto-paginated, up to 500,000) to a CSV file on this computer and return its path plus a preview.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        dimensions: e.g. "query,page" or "date,page,device"
        days: Look-back window when start_date is omitted (default 90)
        start_date: YYYY-MM-DD (optional)
        end_date: YYYY-MM-DD (optional)
        search_type: web, image, video, news, discover, googleNews
        filters: Optional AND filters
        max_rows: Safety cap (default 100000, max 500000)
        file_name: Optional file name; saved in GSC_EXPORT_DIR (default ~/Documents/sam-gsc-exports)
    """

    def work():
        site = gsc.resolve_site(site_url)
        dims = gsc.normalize_dimensions(dimensions)
        state = cfg.SETTINGS.data_state
        start, end, n = gsc.date_range(days, start_date, end_date, state)
        body = gsc.build_query(start, end, dims, search_type=gsc.normalize_search_type(search_type),
                               filters=gsc.normalize_filters(filters), row_limit=25000, data_state=state)
        raw = gsc.fetch_all_rows(site, body, max_rows=gsc.coerce_int(max_rows, 100000, 1, 500000))
        rows = [gsc.format_row(r, dims) for r in raw]
        out_dir = cfg.SETTINGS.export_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", site.lower()).strip("-")
        name = file_name or f"gsc-{slug}-{'-'.join(dims)}-{start}-to-{end}.csv"
        name = re.sub(r"[\\/:*?\"<>|]+", "-", name)
        if not name.lower().endswith(".csv"):
            name += ".csv"
        path = out_dir / name
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=[*dims, "clicks", "impressions", "ctr", "position"])
            writer.writeheader()
            writer.writerows(rows)
        t = gsc.totals(rows)
        return {
            "site_url": site,
            "file": str(path),
            "rows_written": len(rows),
            "date_range": {"start": start, "end": end, "days": n},
            "dimensions": dims,
            "ctr_unit": "percent",
            "totals": {k: v for k, v in t.items() if k != "rows"},
            "preview": rows[:10],
        }

    return await _call("exporting search analytics", work, site_url=site_url)


# =========================================================================== INSIGHTS

def _query_page_rows(site_url: Optional[str], days: int, search_type: str = "web", max_rows: int = 25000, filters=None):
    site = gsc.resolve_site(site_url)
    state = cfg.SETTINGS.data_state
    start, end, n = gsc.date_range(days, None, None, state)
    body = gsc.build_query(start, end, ["query", "page"], search_type=gsc.normalize_search_type(search_type),
                           filters=gsc.normalize_filters(filters), row_limit=25000, data_state=state)
    rows = [gsc.format_row(r, ["query", "page"]) for r in gsc.fetch_all_rows(site, body, max_rows=max_rows)]
    return site, {"start": start, "end": end, "days": n}, rows


@tool("insights", "Striking-distance keywords")
async def find_striking_distance_keywords(
    site_url: Optional[str] = None,
    days: int = 28,
    min_position: float = 4,
    max_position: float = 20,
    min_impressions: int = 50,
    limit: int = 30,
) -> str:
    """Quick wins: queries ranking just off the top spots (default positions 4-20) with real impressions, ranked by estimated extra clicks if they reached position 3.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        days: Days to analyse (default 28)
        min_position: Lowest position to include (default 4)
        max_position: Highest position to include (default 20)
        min_impressions: Ignore rows below this (default 50)
        limit: Rows to return (default 30)
    """

    def work():
        site, rng, rows = _query_page_rows(site_url, days)
        lo, hi = gsc.coerce_float(min_position, 4), gsc.coerce_float(max_position, 20)
        min_imp = gsc.coerce_int(min_impressions, 50, 0)
        target = reference.expected_ctr(3)
        picks = []
        for r in rows:
            if lo <= r["position"] <= hi and r["impressions"] >= min_imp:
                gain = max(0.0, r["impressions"] * (target - r["ctr"]) / 100)
                picks.append({**r, "est_extra_clicks_at_pos3": round(gain), "page_bucket": "page 1" if r["position"] <= 10 else "page 2"})
        picks.sort(key=lambda x: x["est_extra_clicks_at_pos3"], reverse=True)
        return {
            "site_url": site, "date_range": rng, "ctr_unit": "percent",
            "criteria": {"position": [lo, hi], "min_impressions": min_imp},
            "matches": len(picks),
            "estimate_note": "Extra clicks use a generic CTR curve (~11% at position 3) — treat as a rough priority score.",
            "rows": picks[: gsc.coerce_int(limit, 30, 1, 1000)],
            "next_steps": [
                "Improve title/H1 and intro to match the query intent exactly.",
                "Add internal links from strong pages using the query as anchor text.",
                "Expand the section answering the query; add FAQ or comparison content where relevant.",
            ],
        }

    return await _call("finding striking-distance keywords", work, site_url=site_url)


@tool("insights", "Keyword cannibalization")
async def find_keyword_cannibalization(
    site_url: Optional[str] = None,
    days: int = 28,
    min_impressions: int = 20,
    min_share: float = 10,
    limit: int = 20,
) -> str:
    """Find queries where two or more of your pages compete, with a suggested primary page and fix for each.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        days: Days to analyse (default 28)
        min_impressions: Minimum impressions for a page to count on a query (default 20)
        min_share: A competing page must hold at least this % of the query's impressions (default 10)
        limit: Number of conflicts to return (default 20)
    """

    def work():
        site, rng, rows = _query_page_rows(site_url, days)
        by_query: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r["impressions"] >= gsc.coerce_int(min_impressions, 20, 0):
                by_query[r["query"]].append(r)
        share_min = gsc.coerce_float(min_share, 10)
        conflicts = []
        for q, pages in by_query.items():
            total_imp = sum(p["impressions"] for p in pages)
            strong = [p for p in pages if total_imp and p["impressions"] / total_imp * 100 >= share_min]
            if len(strong) < 2:
                continue
            strong.sort(key=lambda p: (p["position"], -p["clicks"]))
            primary = strong[0]
            severity = "high" if total_imp >= 1000 else ("medium" if total_imp >= 200 else "low")
            conflicts.append(
                {
                    "query": q,
                    "total_impressions": total_imp,
                    "total_clicks": sum(p["clicks"] for p in strong),
                    "severity": severity,
                    "suggested_primary_page": primary["page"],
                    "pages": [{k: p[k] for k in ("page", "clicks", "impressions", "ctr", "position")} for p in strong],
                    "suggested_fix": "Merge/redirect the weaker page into the primary, or differentiate intent and add a canonical/internal link to the primary.",
                }
            )
        conflicts.sort(key=lambda c: c["total_impressions"], reverse=True)
        return {
            "site_url": site, "date_range": rng, "ctr_unit": "percent",
            "conflicts_found": len(conflicts),
            "note": "Sitelinks and very broad queries can show multiple pages naturally — review before merging.",
            "conflicts": conflicts[: gsc.coerce_int(limit, 20, 1, 500)],
        }

    return await _call("checking keyword cannibalization", work, site_url=site_url)


@tool("insights", "Brand vs non-brand")
async def get_brand_vs_nonbrand(site_url: Optional[str] = None, brand_terms: Union[str, list[str]] = "", days: int = 28, top_n: int = 10) -> str:
    """Split traffic into branded vs non-branded queries: share of clicks/impressions, CTR, position and top queries for each.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        brand_terms: Brand name plus variants/misspellings, comma separated, e.g. "acme,acme corp,akme"
        days: Days to analyse (default 28)
        top_n: Top queries to list per segment (default 10)
    """

    def work():
        terms = gsc.parse_list(brand_terms)
        if not terms:
            raise ToolError("brand_terms is required, e.g. 'acme,acme corp,akme'.")
        site = gsc.resolve_site(site_url)
        state = cfg.SETTINGS.data_state
        start, end, n = gsc.date_range(days, None, None, state)
        pattern = "(?i)(" + "|".join(re.escape(t) for t in terms) + ")"
        seg: dict[str, Any] = {}
        for label, op in (("branded", "includingRegex"), ("non_branded", "excludingRegex")):
            flt = [{"dimension": "query", "operator": op, "expression": pattern}]
            total = gsc.run_query(site, gsc.build_query(start, end, [], filters=flt, row_limit=1, data_state=state))
            top = gsc.run_query(site, gsc.build_query(start, end, ["query"], filters=flt, row_limit=gsc.coerce_int(top_n, 10, 1, 100), data_state=state))
            t = gsc.totals(total) if total else {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}
            t.pop("rows", None)
            seg[label] = {"totals": t, "top_queries": [gsc.format_row(r, ["query"]) for r in top]}
        all_clicks = seg["branded"]["totals"]["clicks"] + seg["non_branded"]["totals"]["clicks"]
        all_imps = seg["branded"]["totals"]["impressions"] + seg["non_branded"]["totals"]["impressions"]
        return {
            "site_url": site, "date_range": {"start": start, "end": end, "days": n},
            "brand_regex": pattern, "ctr_unit": "percent",
            "branded_click_share_pct": round(seg["branded"]["totals"]["clicks"] / all_clicks * 100, 1) if all_clicks else 0,
            "branded_impression_share_pct": round(seg["branded"]["totals"]["impressions"] / all_imps * 100, 1) if all_imps else 0,
            **seg,
            "note": "Anonymised queries are excluded from query-filtered results, so segment totals can be below the site total.",
        }

    return await _call("splitting brand vs non-brand", work, site_url=site_url)


@tool("insights", "Low-CTR opportunities")
async def find_low_ctr_opportunities(
    site_url: Optional[str] = None,
    days: int = 28,
    max_position: float = 5,
    max_ctr: float = 2.0,
    min_impressions: int = 100,
    limit: int = 30,
) -> str:
    """Pages that rank on top (default position <= 5) but get few clicks (CTR <= 2%): title/meta rewrites, or answers being shown in AI Overviews / featured snippets.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        days: Days to analyse (default 28)
        max_position: Only rows at or above this position (default 5)
        max_ctr: CTR threshold in percent (default 2.0)
        min_impressions: Ignore rows below this (default 100)
        limit: Rows to return (default 30)
    """

    def work():
        site, rng, rows = _query_page_rows(site_url, days)
        mp, mc = gsc.coerce_float(max_position, 5), gsc.coerce_float(max_ctr, 2.0)
        mi = gsc.coerce_int(min_impressions, 100, 0)
        picks = []
        for r in rows:
            if r["position"] <= mp and r["ctr"] <= mc and r["impressions"] >= mi:
                expected = reference.expected_ctr(r["position"])
                picks.append({**r, "expected_ctr": round(expected, 1), "lost_clicks_est": round(r["impressions"] * (expected - r["ctr"]) / 100),
                              "pattern": "silent reference (likely AI Overview / snippet)" if r["position"] <= 1.5 else "weak title/meta"})
        picks.sort(key=lambda x: x["lost_clicks_est"], reverse=True)
        return {
            "site_url": site, "date_range": rng, "ctr_unit": "percent",
            "criteria": {"max_position": mp, "max_ctr_pct": mc, "min_impressions": mi},
            "matches": len(picks),
            "rows": picks[: gsc.coerce_int(limit, 30, 1, 1000)],
            "next_steps": [
                "Rewrite the title tag and meta description with a clear benefit, number or year.",
                "For 'silent reference' rows, add a reason to click (tool, template, calculator, pricing, examples).",
                "Check the SERP manually for AI Overviews, featured snippets or ads pushing you down.",
            ],
        }

    return await _call("finding low-CTR opportunities", work, site_url=site_url)


# =========================================================================== INSPECTION

@tool("inspection", "Inspect URL (full)")
async def inspect_url_enhanced(site_url: Optional[str] = None, page_url: str = "", language_code: Optional[str] = None, include_raw: bool = False) -> str:
    """Full URL Inspection: index verdict, coverage, last crawl, canonicals, robots, fetch state, rich results (with issues), mobile usability and AMP.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        page_url: Full URL to inspect (must belong to the property)
        language_code: Optional language for issue messages, e.g. "en-US"
        include_raw: Also return Google's raw response (default false)
    """

    def work():
        if not page_url:
            raise ToolError("page_url is required.")
        site = gsc.resolve_site(site_url)
        resp = inspection.inspect_raw(site, page_url, language_code)
        if not resp or "inspectionResult" not in resp:
            return {"url": page_url, "message": "No inspection data returned."}
        out = inspection.summarize(page_url, site, resp, full=True, include_raw=gsc.coerce_bool(include_raw))
        out["issues"] = inspection.classify(out)
        return out

    return await _call("inspecting a URL", work, site_url=site_url)


@tool("inspection", "Quick indexing status")
async def check_url_status(site_url: Optional[str] = None, page_url: str = "") -> str:
    """Quick yes/no: is this URL indexed? Plus coverage state, last crawl, canonical and robots/fetch status.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        page_url: Full URL to check
    """

    def work():
        if not page_url:
            raise ToolError("page_url is required.")
        site = gsc.resolve_site(site_url)
        row = inspection.inspect_one(site, page_url, full=False)
        row.pop("rich_results", None)
        return row

    return await _call("checking URL status", work, site_url=site_url)


def _url_list(urls: Any) -> list[str]:
    url_list = gsc.parse_urls(urls)
    if not url_list:
        raise ToolError("No URLs provided. Pass one URL per line (or a JSON array).")
    cap = cfg.SETTINGS.max_batch_urls
    if len(url_list) > cap:
        raise ToolError(
            f"Too many URLs ({len(url_list)}). The limit is {cap} per call.",
            ["Split into smaller batches, or raise GSC_MAX_BATCH_URLS (max 100). URL Inspection quota is 2,000/day and 600/min per property."],
        )
    return url_list


@tool("inspection", "Batch URL inspection")
async def batch_url_inspection(site_url: Optional[str] = None, urls: Union[str, list[str]] = "") -> str:
    """Inspect several URLs at once (concurrently). Returns index verdict, coverage, last crawl and rich results per URL.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        urls: URLs, one per line or a JSON array (default max 10, see GSC_MAX_BATCH_URLS)
    """
    try:
        url_list = _url_list(urls)
        site = await asyncio.to_thread(gsc.resolve_site, site_url)
        await asyncio.to_thread(auth.get_credentials)  # refresh once before going concurrent
        results = await inspection.inspect_many(site, url_list, full=False)
        return dumps({"site_url": site, "count": len(results), "results": results})
    except Exception as exc:
        return describe_exception(exc, "inspecting URLs", site_url)


@tool("inspection", "Check indexing issues")
async def check_indexing_issues(site_url: Optional[str] = None, urls: Union[str, list[str]] = "") -> str:
    """Check several URLs and group them into issue buckets: not indexed, canonical mismatch, robots blocked, noindex, fetch errors, rich-result issues.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        urls: URLs, one per line or a JSON array
    """
    try:
        url_list = _url_list(urls)
        site = await asyncio.to_thread(gsc.resolve_site, site_url)
        await asyncio.to_thread(auth.get_credentials)
        results = await inspection.inspect_many(site, url_list, full=False)
        buckets: dict[str, list] = defaultdict(list)
        for row in results:
            for b in inspection.classify(row):
                if b == "indexed":
                    buckets[b].append(row["url"])
                elif b == "canonical_issues":
                    buckets[b].append(f"{row['url']} — Google chose {row['google_canonical']} instead of {row['user_canonical']}")
                elif b == "errors":
                    buckets[b].append(f"{row['url']} — {row.get('error')}")
                elif b == "rich_result_issues":
                    buckets[b].append({"url": row["url"], "issues": (row.get("rich_results") or {}).get("issues")})
                else:
                    buckets[b].append(f"{row['url']} — {row.get('coverage_state') or row.get('page_fetch_state') or row.get('indexing_state')}")
        summary = {k: len(v) for k, v in buckets.items()}
        summary["total_checked"] = len(url_list)
        return dumps({"site_url": site, "summary": summary, "issues": {k: v for k, v in buckets.items() if k != "indexed"},
                      "indexed_urls": buckets.get("indexed", [])})
    except Exception as exc:
        return describe_exception(exc, "checking indexing issues", site_url)


async def _sample_urls(site: str, source: str, urls: Any, sitemap_url: Optional[str], limit: int, days: int) -> list[str]:
    if urls:
        return gsc.parse_urls(urls)[:limit]
    source = (source or "top_pages").lower()
    if source == "sitemap":
        if not sitemap_url:
            sitemaps = await asyncio.to_thread(lambda: gsc.execute(gsc.service().sitemaps().list(siteUrl=site)))
            paths = [s.get("path") for s in sitemaps.get("sitemap", []) if s.get("path")]
            if not paths:
                raise ToolError("No sitemap submitted for this property. Pass sitemap_url or use source='top_pages'.")
            sitemap_url = paths[0]
        return await asyncio.to_thread(inspection.urls_from_sitemap, sitemap_url, limit)
    state = cfg.SETTINGS.data_state
    start, end, _ = gsc.date_range(days, None, None, state)
    rows = await asyncio.to_thread(gsc.run_query, site, gsc.build_query(start, end, ["page"], row_limit=limit, data_state=state))
    return [r["keys"][0] for r in rows]


@tool("inspection", "Index coverage report")
async def get_index_coverage(
    site_url: Optional[str] = None,
    source: str = "top_pages",
    urls: Union[str, list[str], None] = None,
    sitemap_url: Optional[str] = None,
    limit: int = 20,
    days: int = 28,
    issue_filter: Optional[str] = None,
) -> str:
    """Coverage report built from live URL Inspection: groups URLs by Google's coverage state with counts and example URLs.

    The public API has no bulk coverage endpoint, so this samples URLs from your top pages, a sitemap, or a list you give.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        source: "top_pages" (pages with impressions, default) or "sitemap"
        urls: Optional explicit URLs (overrides source)
        sitemap_url: Sitemap to read when source="sitemap" (defaults to the first submitted sitemap)
        limit: How many URLs to inspect (default 20, max GSC_MAX_BATCH_URLS x 5)
        days: Window for picking top pages (default 28)
        issue_filter: Only return states containing this text, e.g. "crawled" or "duplicate"
    """
    try:
        site = await asyncio.to_thread(gsc.resolve_site, site_url)
        cap = min(cfg.SETTINGS.max_batch_urls * 5, 100)
        n = gsc.coerce_int(limit, 20, 1, cap)
        url_list = await _sample_urls(site, source, urls, sitemap_url, n, days)
        if not url_list:
            return error_payload("Found no URLs to inspect.", ["Pass urls, or pick a longer days window / another sitemap."])
        await asyncio.to_thread(auth.get_credentials)
        results = await inspection.inspect_many(site, url_list, full=False)
        states: dict[str, dict[str, Any]] = {}
        verdicts: dict[str, int] = defaultdict(int)
        for r in results:
            state = r.get("coverage_state") or ("Inspection error" if "error" in r else "Unknown")
            verdicts[r.get("index_verdict", "ERROR")] += 1
            s = states.setdefault(state, {"coverage_state": state, "count": 0, "example_urls": []})
            s["count"] += 1
            if len(s["example_urls"]) < 10:
                s["example_urls"].append(r["url"])
        items = sorted(states.values(), key=lambda x: x["count"], reverse=True)
        if issue_filter:
            items = [i for i in items if issue_filter.lower() in i["coverage_state"].lower()]
        return dumps(
            {
                "site_url": site,
                "source": "urls" if urls else source,
                "inspected": len(results),
                "verdicts": dict(verdicts),
                "coverage_states": items,
                "canonical_mismatches": [r["url"] for r in results if r.get("canonical_mismatch")],
                "note": "Sample-based. For full-site numbers open the Page indexing report in Search Console.",
            }
        )
    except Exception as exc:
        return describe_exception(exc, "building the coverage report", site_url)


@tool("inspection", "Mobile signals")
async def get_mobile_issues(
    site_url: Optional[str] = None,
    urls: Union[str, list[str], None] = None,
    source: str = "top_pages",
    limit: int = 10,
    issue_filter: Optional[str] = None,
) -> str:
    """Mobile signals per URL from URL Inspection: crawled-as (smartphone/desktop), fetch state and any mobile-usability verdict/issues Google still returns.

    Note: Google retired the Mobile Usability report in Dec 2023, so the usability verdict is often empty; use Lighthouse/PageSpeed for layout checks.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        urls: Optional URLs (one per line). Defaults to your top pages.
        source: "top_pages" or "sitemap" when urls is empty
        limit: URLs to check (default 10)
        issue_filter: Only return URLs whose issue types contain this text
    """
    try:
        site = await asyncio.to_thread(gsc.resolve_site, site_url)
        n = gsc.coerce_int(limit, 10, 1, cfg.SETTINGS.max_batch_urls * 5)
        url_list = await _sample_urls(site, source, urls, None, n, 28)
        await asyncio.to_thread(auth.get_credentials)
        results = await inspection.inspect_many(site, url_list, full=True)
        rows = []
        for r in results:
            mob = r.get("mobile_usability") or {}
            row = {
                "url": r["url"],
                "crawled_as": r.get("crawled_as"),
                "page_fetch_state": r.get("page_fetch_state"),
                "mobile_verdict": mob.get("verdict", "NOT_REPORTED"),
                "mobile_issues": mob.get("issues", []),
            }
            if "error" in r:
                row["error"] = r["error"]
            if issue_filter and not any(issue_filter.lower() in str(i.get("type", "")).lower() for i in row["mobile_issues"]):
                continue
            rows.append(row)
        return dumps(
            {
                "site_url": site,
                "checked": len(results),
                "crawled_as_desktop": [r["url"] for r in rows if r.get("crawled_as") == "DESKTOP"],
                "results": rows,
                "note": "Mobile Usability was retired by Google in Dec 2023; NOT_REPORTED is normal.",
            }
        )
    except Exception as exc:
        return describe_exception(exc, "checking mobile signals", site_url)


# =========================================================================== INDEXING API

@tool("indexing", "Request indexing (Indexing API)", read_only=False, idempotent=False, requires="indexing")
async def request_indexing(urls: Union[str, list[str]] = "", notification_type: str = "URL_UPDATED") -> str:
    """Notify Google that URLs were added/updated (or removed) via the official Indexing API.

    Google officially supports this only for pages with JobPosting or BroadcastEvent (livestream) markup.
    Needs GSC_ENABLE_INDEXING_API=true, the Indexing API enabled in Google Cloud, and OWNER permission on the property.
    Default quota: 200 publish requests per day.

    Args:
        urls: URLs, one per line or a JSON array (max 100 per call)
        notification_type: URL_UPDATED (default) or URL_DELETED (needs GSC_ALLOW_DESTRUCTIVE=true)
    """
    ntype = str(notification_type or "URL_UPDATED").upper()
    if ntype not in ("URL_UPDATED", "URL_DELETED"):
        return error_payload("notification_type must be URL_UPDATED or URL_DELETED.")
    if ntype == "URL_DELETED":
        blocked = _destructive_blocked("request_indexing (URL_DELETED)")
        if blocked:
            return blocked

    def work():
        url_list = gsc.parse_urls(urls)
        if not url_list:
            raise ToolError("No URLs provided.")
        if len(url_list) > 100:
            raise ToolError("Max 100 URLs per call (and 200 per day by default).")
        svc = auth.build_service("indexing", "v3")
        results = []
        for u in url_list:
            try:
                resp = gsc.execute(svc.urlNotifications().publish(body={"url": u, "type": ntype}))
                meta = resp.get("urlNotificationMetadata", {})
                latest = meta.get("latestUpdate") or meta.get("latestRemove") or {}
                results.append({"url": u, "status": "submitted", "notify_time": latest.get("notifyTime"), "type": latest.get("type", ntype)})
            except Exception as exc:
                status, message, _ = gsc._http_details(exc)
                results.append({"url": u, "status": "failed", "error": f"HTTP {status}: {message}" if status else str(exc)})
        ok = sum(1 for r in results if r["status"] == "submitted")
        return {
            "notification_type": ntype,
            "submitted": ok,
            "failed": len(results) - ok,
            "results": results,
            "note": "Submission is a hint, not a guarantee of indexing. Check later with get_indexing_status or inspect_url_enhanced.",
        }

    return await _call("requesting indexing", work)


@tool("indexing", "Indexing API status", requires="indexing")
async def get_indexing_status(url: str) -> str:
    """Last Indexing API notification Google received for a URL (time and type).

    Args:
        url: The exact URL previously sent with request_indexing
    """

    def work():
        svc = auth.build_service("indexing", "v3")
        meta = gsc.execute(svc.urlNotifications().getMetadata(url=url))
        return {"url": url, "latest_update": meta.get("latestUpdate"), "latest_remove": meta.get("latestRemove")}

    return await _call("reading Indexing API status", work)


# =========================================================================== SITEMAPS

def _sitemap_row(s: dict[str, Any]) -> dict[str, Any]:
    errors, warnings = int(s.get("errors", 0) or 0), int(s.get("warnings", 0) or 0)
    contents = [{"type": c.get("type", "unknown"), "submitted": int(c.get("submitted", 0) or 0), "indexed": c.get("indexed")}
                for c in s.get("contents", []) or []]
    return {
        "path": s.get("path"),
        "type": "index" if s.get("isSitemapsIndex") else "sitemap",
        "status": "has errors" if errors else ("has warnings" if warnings else ("pending" if s.get("isPending") else "ok")),
        "is_pending": bool(s.get("isPending", False)),
        "last_submitted": gsc.fmt_time(s.get("lastSubmitted")),
        "last_downloaded": gsc.fmt_time(s.get("lastDownloaded")),
        "errors": errors,
        "warnings": warnings,
        "urls_submitted": sum(c["submitted"] for c in contents if c["type"] in ("web", "WEB")) or None,
        "contents": contents,
    }


@tool("sitemaps", "List sitemaps")
async def get_sitemaps(site_url: Optional[str] = None) -> str:
    """All submitted sitemaps with status, last download, errors/warnings and submitted URL counts by type.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
    """

    def work():
        site = gsc.resolve_site(site_url)
        resp = gsc.execute(gsc.service().sitemaps().list(siteUrl=site))
        items = [_sitemap_row(s) for s in resp.get("sitemap", [])]
        if not items:
            return {"site_url": site, "count": 0, "sitemaps": [], "hint": "No sitemaps submitted. Use submit_sitemap."}
        return {"site_url": site, "count": len(items), "with_errors": sum(1 for i in items if i["errors"]), "sitemaps": items}

    return await _call("listing sitemaps", work, site_url=site_url)


@tool("sitemaps", "List sitemaps (detailed)")
async def list_sitemaps_enhanced(site_url: Optional[str] = None, sitemap_index: Optional[str] = None) -> str:
    """Detailed sitemap list, optionally the children of one sitemap index, with pending counts.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        sitemap_index: Optional sitemap index URL to list its child sitemaps
    """

    def work():
        site = gsc.resolve_site(site_url)
        kwargs: dict[str, Any] = {"siteUrl": site}
        if sitemap_index:
            kwargs["sitemapIndex"] = sitemap_index
        resp = gsc.execute(gsc.service().sitemaps().list(**kwargs))
        items = [_sitemap_row(s) for s in resp.get("sitemap", [])]
        return {
            "site_url": site,
            "sitemap_index": sitemap_index,
            "count": len(items),
            "pending_count": sum(1 for i in items if i["is_pending"]),
            "error_count": sum(i["errors"] for i in items),
            "warning_count": sum(i["warnings"] for i in items),
            "sitemaps": items,
        }

    return await _call("listing sitemaps", work, site_url=site_url)


@tool("sitemaps", "Sitemap details")
async def get_sitemap_details(site_url: Optional[str] = None, sitemap_url: str = "") -> str:
    """Details for one sitemap: type, processing status, last submitted/downloaded, errors, warnings and content breakdown.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        sitemap_url: Full sitemap URL
    """

    def work():
        if not sitemap_url:
            raise ToolError("sitemap_url is required.")
        site = gsc.resolve_site(site_url)
        details = gsc.execute(gsc.service().sitemaps().get(siteUrl=site, feedpath=sitemap_url))
        row = _sitemap_row(details)
        row["site_url"] = site
        row["note"] = "Google no longer reports 'indexed' counts per sitemap; use get_index_coverage with source='sitemap'."
        return row

    return await _call("reading sitemap details", work, site_url=site_url)


@tool("sitemaps", "Submit sitemap", read_only=False, idempotent=True)
async def submit_sitemap(site_url: Optional[str] = None, sitemap_url: str = "") -> str:
    """Submit a new sitemap or resubmit an existing one.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        sitemap_url: Full sitemap URL, e.g. https://example.com/sitemap.xml
    """

    def work():
        if not sitemap_url:
            raise ToolError("sitemap_url is required.")
        site = gsc.resolve_site(site_url)
        svc = gsc.service()
        gsc.execute(svc.sitemaps().submit(siteUrl=site, feedpath=sitemap_url))
        out: dict[str, Any] = {"status": "submitted", "site_url": site, "sitemap_url": sitemap_url}
        try:
            out["sitemap"] = _sitemap_row(gsc.execute(svc.sitemaps().get(siteUrl=site, feedpath=sitemap_url)))
        except Exception:
            pass
        out["note"] = "Google processes sitemaps asynchronously — check back later with get_sitemap_details."
        return out

    return await _call("submitting a sitemap", work, site_url=site_url)


@tool("sitemaps", "Delete sitemap", read_only=False, destructive=True)
async def delete_sitemap(site_url: Optional[str] = None, sitemap_url: str = "") -> str:
    """Remove (unsubmit) a sitemap from Search Console (requires GSC_ALLOW_DESTRUCTIVE=true). Already-indexed URLs stay indexed.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        sitemap_url: Full sitemap URL
    """
    blocked = _destructive_blocked("delete_sitemap")
    if blocked:
        return blocked

    def work():
        if not sitemap_url:
            raise ToolError("sitemap_url is required.")
        site = gsc.resolve_site(site_url)
        svc = gsc.service()
        try:
            gsc.execute(svc.sitemaps().get(siteUrl=site, feedpath=sitemap_url))
        except Exception as exc:
            if gsc._http_details(exc)[0] == 404:
                return {"status": "not_found", "sitemap_url": sitemap_url, "message": "Not submitted (or already removed)."}
            raise
        gsc.execute(svc.sitemaps().delete(siteUrl=site, feedpath=sitemap_url))
        return {"status": "deleted", "site_url": site, "sitemap_url": sitemap_url}

    return await _call("deleting a sitemap", work, site_url=site_url)


@tool("sitemaps", "Manage sitemaps (all-in-one)", read_only=False)
async def manage_sitemaps(site_url: Optional[str] = None, action: str = "list", sitemap_url: Optional[str] = None, sitemap_index: Optional[str] = None) -> str:
    """All-in-one sitemap tool: action = list, details, submit or delete.

    Args:
        site_url: Exact property (defaults to GSC_SITE_URL)
        action: list, details, submit or delete
        sitemap_url: Needed for details, submit and delete
        sitemap_index: Optional index URL for action=list
    """
    act = (action or "list").strip().lower()
    if act == "list":
        return await list_sitemaps_enhanced(site_url, sitemap_index)
    if act not in ("details", "submit", "delete"):
        return error_payload(f"Invalid action '{action}'.", ["Use list, details, submit or delete."])
    if not sitemap_url:
        return error_payload(f"The {act} action needs sitemap_url.")
    if act == "details":
        return await get_sitemap_details(site_url, sitemap_url)
    if act == "submit":
        if cfg.SETTINGS.read_only:
            return error_payload("Read-only mode (GSC_READ_ONLY=true) — submitting is disabled.")
        return await submit_sitemap(site_url, sitemap_url)
    return await delete_sitemap(site_url, sitemap_url)


# =========================================================================== COMPAT ALIASES
# Alternative tool names, so prompts written with these common names keep working.

@tool("properties", "List sites (alias)", requires="aliases", name="list_sites")
async def _alias_list_sites() -> str:
    """Alias of list_properties."""
    return await list_properties()


@tool("properties", "List GSC sites (alias)", requires="aliases", name="list_gsc_sites")
async def _alias_list_gsc_sites() -> str:
    """Alias of list_properties."""
    return await list_properties()


@tool("analytics", "Performance data (alias)", requires="aliases", name="get_performance_data")
async def _alias_get_performance_data(
    site_url: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    dimensions: DimArg = "query",
    filter_query: Optional[str] = None,
    filter_page: Optional[str] = None,
    filter_country: Optional[str] = None,
    filter_device: Optional[str] = None,
    row_limit: int = 1000,
) -> str:
    """Alias of get_advanced_search_analytics with shortcut filters (filter_query, filter_page, filter_country, filter_device)."""
    flt = []
    for dim, val, op in (("query", filter_query, "contains"), ("page", filter_page, "contains"),
                         ("country", filter_country, "equals"), ("device", filter_device, "equals")):
        if val:
            flt.append({"dimension": dim, "operator": op, "expression": val})
    return await get_advanced_search_analytics(site_url=site_url, start_date=start_date, end_date=end_date,
                                               dimensions=dimensions, row_limit=row_limit, filters=flt or None)


@tool("inspection", "URL inspection (alias)", requires="aliases", name="get_url_inspection_result")
async def _alias_get_url_inspection_result(site_url: Optional[str] = None, page_url: str = "") -> str:
    """Alias of inspect_url_enhanced."""
    return await inspect_url_enhanced(site_url, page_url)


@tool("sitemaps", "Sitemap data (alias)", requires="aliases", name="get_sitemap_data")
async def _alias_get_sitemap_data(site_url: Optional[str] = None) -> str:
    """Alias of list_sitemaps_enhanced."""
    return await list_sitemaps_enhanced(site_url)


@tool("indexing", "Submit URL (alias)", read_only=False, idempotent=False, requires="aliases", name="submit_url")
async def _alias_submit_url(site_url: Optional[str] = None, page_url: str = "") -> str:
    """Alias of request_indexing for one URL. Uses the real Indexing API when GSC_ENABLE_INDEXING_API=true."""
    if not cfg.SETTINGS.enable_indexing_api:
        return error_payload(
            "Direct indexing requests need the Indexing API, which is off.",
            ["Set GSC_ENABLE_INDEXING_API=true (see README), or use inspect_url_enhanced and click 'Request indexing' in Search Console."],
        )
    return await request_indexing(page_url)


# =========================================================================== RESOURCES

def _register_resources() -> None:
    for item in skills.list_skills():
        sid = item["id"]

        def make(skill_id: str = sid):
            def _read() -> str:
                data = skills.read_skill(skill_id)
                return data["content"] if data else ""

            _read.__name__ = f"skill_{skill_id.replace('-', '_')}"
            return _read

        try:
            mcp.resource(item["uri"], name=f"skill-{sid}", description=item["description"] or sid, mime_type="text/markdown")(make())
        except Exception as exc:  # resources are optional
            log.warning("Could not register resource %s: %s", item["uri"], exc)

    def _ref() -> str:
        return dumps({"dimensions": reference.DIMENSIONS, "metrics": reference.METRICS, "operators": reference.OPERATORS,
                      "search_types": reference.SEARCH_TYPES})

    try:
        mcp.resource("gsc://reference", name="gsc-reference", description="Dimensions, metrics, operators and search types",
                     mime_type="application/json")(_ref)
    except Exception as exc:
        log.warning("Could not register reference resource: %s", exc)


_register_resources()

from . import prompts  # noqa: E402

prompts.register(mcp)


def main() -> None:
    from .compat import run

    s = cfg.SETTINGS
    log.info("Starting Sam GSC MCP %s (mcp SDK %s, transport %s)", __version__, SDK_MAJOR, s.transport)
    if s.transport not in ("stdio", "sse", "streamable-http"):
        raise SystemExit(f"Unknown MCP_TRANSPORT '{s.transport}'. Use stdio (default), sse or streamable-http.")
    run(mcp, s.transport, s.host, s.port, s.http_path)


if __name__ == "__main__":
    main()
