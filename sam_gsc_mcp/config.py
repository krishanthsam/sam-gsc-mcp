"""Runtime configuration for Sam GSC MCP.

Every setting is read from an environment variable first, then from the
optional ``config.json`` that ``setup_gsc_access`` can save in the config
directory, then from a built-in default. Paths accept ``~`` and ``$VARS``.

Only file *paths* and plain settings are ever written to ``config.json`` —
never the contents of a credentials file.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from platformdirs import user_config_dir

log = logging.getLogger("sam_gsc_mcp")

APP_NAME = "sam-gsc-mcp"
TRUTHY = {"1", "true", "yes", "y", "on"}

SCOPE_FULL = "https://www.googleapis.com/auth/webmasters"
SCOPE_READONLY = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_INDEXING = "https://www.googleapis.com/auth/indexing"

ALL_TOOLSETS = (
    "setup",
    "reference",
    "skills",
    "properties",
    "analytics",
    "insights",
    "inspection",
    "indexing",
    "sitemaps",
)


def expand_path(path: Optional[str]) -> Optional[str]:
    """Expand ``~`` and environment variables; return None for empty input."""
    if not path or not str(path).strip():
        return None
    return os.path.expandvars(os.path.expanduser(str(path).strip().strip('"').strip("'")))


def _config_dir() -> Path:
    raw = expand_path(os.environ.get("GSC_CONFIG_DIR"))
    path = Path(raw) if raw else Path(user_config_dir(APP_NAME))
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # read-only home in some containers
        log.warning("Could not create config dir %s: %s", path, exc)
    return path


def _load_saved(config_dir: Path) -> dict[str, Any]:
    file = config_dir / "config.json"
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning("Ignoring unreadable %s: %s", file, exc)
        return {}


@dataclass
class Settings:
    """Resolved settings. Re-create with :func:`load_settings` to refresh."""

    config_dir: Path
    token_file: Path
    export_dir: Path
    saved: dict[str, Any] = field(default_factory=dict)

    # Auth
    auth_mode: str = "auto"  # auto | oauth | service_account | adc
    oauth_client_secrets_file: Optional[str] = None
    oauth_client_secrets_explicit: bool = False
    credentials_path: Optional[str] = None
    oauth_port: int = 0
    oauth_timeout: int = 300

    # Behaviour
    site_url: Optional[str] = None
    data_state: str = "all"
    allow_destructive: bool = False
    read_only: bool = False
    enable_indexing_api: bool = False
    max_batch_urls: int = 10
    inspection_concurrency: int = 10
    api_retries: int = 3
    compat_aliases: bool = False
    toolsets: tuple[str, ...] = ALL_TOOLSETS
    disabled_tools: frozenset[str] = frozenset()
    update_check: bool = True

    # Transport
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 3001
    http_path: str = "/mcp"

    @property
    def scopes(self) -> list[str]:
        scopes = [SCOPE_READONLY if self.read_only else SCOPE_FULL]
        if self.enable_indexing_api and not self.read_only:
            scopes.append(SCOPE_INDEXING)
        return scopes

    @property
    def script_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def possible_service_account_paths(self) -> list[str]:
        """Explicit path first, then clone-install fallbacks."""
        candidates = [
            self.credentials_path,
            str(Path.cwd() / "service_account_credentials.json"),
            str(self.script_dir.parent / "service_account_credentials.json"),
        ]
        seen, out = set(), []
        for c in candidates:
            if c and c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def possible_client_secret_paths(self) -> list[str]:
        """Explicit path first, then the common default file names."""
        if self.oauth_client_secrets_file:
            return [self.oauth_client_secrets_file]
        out = []
        for base in (Path.cwd(), self.script_dir.parent, self.config_dir):
            for name in ("client_secrets.json", "credentials.json"):
                out.append(str(base / name))
        return out

    def describe(self) -> dict[str, Any]:
        """Safe, secret-free summary for get_capabilities."""
        return {
            "auth_mode": self.auth_mode,
            "oauth_client_secrets_file": self.oauth_client_secrets_file,
            "credentials_path": self.credentials_path,
            "default_site_url": self.site_url,
            "data_state": self.data_state,
            "read_only": self.read_only,
            "allow_destructive": self.allow_destructive,
            "indexing_api_enabled": self.enable_indexing_api,
            "max_batch_urls": self.max_batch_urls,
            "toolsets": list(self.toolsets),
            "compat_aliases": self.compat_aliases,
            "config_dir": str(self.config_dir),
            "token_file": str(self.token_file),
            "export_dir": str(self.export_dir),
            "transport": self.transport,
        }


def _get(name: str, saved: dict, saved_key: Optional[str] = None, default: Any = None, aliases: tuple = ()) -> Any:
    for key in (name, *aliases):
        val = os.environ.get(key)
        if val is not None and str(val).strip() != "":
            return val
    if saved_key and saved.get(saved_key) not in (None, ""):
        return saved[saved_key]
    return default


def _bool(val: Any, default: bool = False) -> bool:
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in TRUTHY


def _int(val: Any, default: int, lo: int, hi: int) -> int:
    try:
        num = int(str(val).strip()) if val not in (None, "") else default
    except ValueError:
        num = default
    return max(lo, min(hi, num))


def load_settings() -> Settings:
    config_dir = _config_dir()
    saved = _load_saved(config_dir)

    token_raw = expand_path(_get("GSC_TOKEN_FILE", saved))
    token_file = Path(token_raw) if token_raw else config_dir / "token.json"

    export_raw = expand_path(_get("GSC_EXPORT_DIR", saved, "export_dir"))
    export_dir = Path(export_raw) if export_raw else Path.home() / "Documents" / "sam-gsc-exports"

    secrets_env = expand_path(_get("GSC_OAUTH_CLIENT_SECRETS_FILE", saved, aliases=("GSC_CLIENT_SECRETS_FILE",)))
    secrets_saved = expand_path(saved.get("oauth_client_secrets_file"))
    creds_path = expand_path(
        _get("GSC_CREDENTIALS_PATH", saved, "credentials_path", aliases=("GOOGLE_APPLICATION_CREDENTIALS",))
    )

    auth_mode = str(_get("GSC_AUTH_MODE", saved, "auth_mode", "auto")).strip().lower()
    if _bool(os.environ.get("GSC_SKIP_OAUTH")):
        auth_mode = "service_account"
    if auth_mode in ("sa", "service-account", "serviceaccount"):
        auth_mode = "service_account"
    if auth_mode not in ("auto", "oauth", "service_account", "adc"):
        log.warning("Unknown GSC_AUTH_MODE %r, using 'auto'", auth_mode)
        auth_mode = "auto"

    data_state = str(_get("GSC_DATA_STATE", saved, "data_state", "all")).strip().lower()
    if data_state not in ("all", "final"):
        print(
            f"[sam-gsc-mcp] Invalid GSC_DATA_STATE {data_state!r}; use 'all' or 'final'. Falling back to 'all'.",
            file=sys.stderr,
        )
        data_state = "all"

    raw_sets = _get("GSC_TOOLSETS", saved, "toolsets")
    if isinstance(raw_sets, list):
        raw_sets = ",".join(raw_sets)
    if raw_sets and str(raw_sets).strip().lower() not in ("all", "*"):
        wanted = {s.strip().lower() for s in str(raw_sets).split(",") if s.strip()}
        wanted.add("setup")  # always keep the setup tools so users can recover
        toolsets = tuple(s for s in ALL_TOOLSETS if s in wanted)
    else:
        toolsets = ALL_TOOLSETS

    disabled = _get("GSC_DISABLED_TOOLS", saved, "disabled_tools", "")
    if isinstance(disabled, list):
        disabled = ",".join(disabled)
    disabled_tools = frozenset(t.strip() for t in str(disabled).split(",") if t.strip())

    transport = str(os.environ.get("MCP_TRANSPORT", "stdio")).strip().lower()
    if transport in ("http", "streamable_http", "streamablehttp"):
        transport = "streamable-http"

    return Settings(
        config_dir=config_dir,
        token_file=token_file,
        export_dir=export_dir,
        saved=saved,
        auth_mode=auth_mode,
        oauth_client_secrets_file=secrets_env or secrets_saved,
        oauth_client_secrets_explicit=bool(secrets_env or secrets_saved),
        credentials_path=creds_path,
        oauth_port=_int(_get("GSC_OAUTH_PORT", saved), 0, 0, 65535),
        oauth_timeout=_int(_get("GSC_OAUTH_TIMEOUT", saved), 300, 30, 3600),
        site_url=(str(_get("GSC_SITE_URL", saved, "site_url")).strip() or None)
        if _get("GSC_SITE_URL", saved, "site_url")
        else None,
        data_state=data_state,
        allow_destructive=_bool(_get("GSC_ALLOW_DESTRUCTIVE", saved, "allow_destructive")),
        read_only=_bool(_get("GSC_READ_ONLY", saved, "read_only")),
        enable_indexing_api=_bool(_get("GSC_ENABLE_INDEXING_API", saved, "enable_indexing_api")),
        max_batch_urls=_int(_get("GSC_MAX_BATCH_URLS", saved, "max_batch_urls"), 10, 1, 100),
        inspection_concurrency=_int(_get("GSC_INSPECTION_CONCURRENCY", saved), 10, 1, 20),
        api_retries=_int(_get("GSC_API_RETRIES", saved), 3, 0, 10),
        compat_aliases=_bool(_get("GSC_COMPAT_ALIASES", saved, "compat_aliases")),
        toolsets=toolsets,
        disabled_tools=disabled_tools,
        update_check=_bool(_get("GSC_UPDATE_CHECK", saved), True),
        transport=transport,
        host=str(os.environ.get("MCP_HOST", "127.0.0.1")),
        port=_int(os.environ.get("MCP_PORT"), 3001, 1, 65535),
        http_path=str(os.environ.get("MCP_PATH", "/mcp")),
    )


def save_settings(updates: dict[str, Any], settings: Settings) -> Path:
    """Merge ``updates`` into config.json (paths and flags only)."""
    allowed = {
        "auth_mode",
        "oauth_client_secrets_file",
        "credentials_path",
        "site_url",
        "data_state",
        "export_dir",
    }
    data = dict(settings.saved)
    for key, val in updates.items():
        if key in allowed:
            if val in (None, ""):
                data.pop(key, None)
            else:
                data[key] = val
    file = settings.config_dir / "config.json"
    file.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return file


SETTINGS = load_settings()


def reload_settings() -> Settings:
    global SETTINGS
    SETTINGS = load_settings()
    return SETTINGS
