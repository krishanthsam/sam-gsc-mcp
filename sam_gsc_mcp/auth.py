"""Google authentication for Sam GSC MCP.

Order in ``auto`` mode:

1. OAuth (your own Google account) — cached token, refreshed automatically.
2. Service account JSON key.
3. Application Default Credentials (``gcloud auth application-default login``).

The OAuth browser flow never prints to stdout, because stdout is the MCP
stdio channel; the consent URL is logged to stderr instead.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import threading
from typing import Any, Optional

from . import config as cfg

log = logging.getLogger("sam_gsc_mcp")

_LOCK = threading.RLock()
_CACHED: dict[str, Any] = {"creds": None, "method": None}


class AuthError(Exception):
    """Raised when no authentication method works. Message is user-facing."""


def reset_cache() -> None:
    with _LOCK:
        _CACHED["creds"] = None
        _CACHED["method"] = None


def current_method() -> Optional[str]:
    return _CACHED.get("method")


def _first_existing(paths: list[Optional[str]]) -> Optional[str]:
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def inspect_credentials_file(path: str) -> tuple[str, Optional[str]]:
    """Return ('missing'|'invalid'|'service_account'|'oauth_client'|'authorized_user', detail).

    Reads only the structural keys — the private key never leaves this check.
    """
    try:
        if not os.path.isfile(path):
            return "missing", None
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return "invalid", "not a JSON object"
        if data.get("type") == "service_account":
            return "service_account", data.get("client_email")
        if "installed" in data or "web" in data:
            kind = "installed" if "installed" in data else "web"
            return "oauth_client", kind
        if data.get("type") == "authorized_user":
            return "authorized_user", None
        return "invalid", "unrecognised Google credentials JSON"
    except json.JSONDecodeError:
        return "invalid", "not valid JSON"
    except Exception as exc:  # pragma: no cover - defensive
        return "invalid", exc.__class__.__name__


def service_account_email() -> Optional[str]:
    path = _first_existing(cfg.SETTINGS.possible_service_account_paths())
    if not path:
        return None
    kind, detail = inspect_credentials_file(path)
    return detail if kind == "service_account" else None


# --------------------------------------------------------------------------- OAuth

def _save_token(creds) -> None:
    token_file = cfg.SETTINGS.token_file
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        try:
            os.chmod(token_file, 0o600)
        except OSError:
            pass
    except OSError as exc:
        log.warning("Could not save OAuth token to %s: %s", token_file, exc)


def _load_token():
    from google.oauth2.credentials import Credentials

    token_file = cfg.SETTINGS.token_file
    if not token_file.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(token_file))
    except Exception as exc:
        log.warning("Discarding unreadable token %s: %s", token_file, exc)
        try:
            token_file.unlink()
        except OSError:
            pass
        return None
    granted = set(creds.scopes or [])
    needed = set(cfg.SETTINGS.scopes)
    # A full-access token also satisfies a read-only request.
    if cfg.SCOPE_FULL in granted:
        granted.add(cfg.SCOPE_READONLY)
    if not needed.issubset(granted):
        log.info("Cached token lacks scopes %s; a new sign-in is needed.", needed - granted)
        return None
    return creds


def run_oauth_flow(client_secrets: str):
    """Open the browser consent screen and return fresh credentials."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    import webbrowser

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, cfg.SETTINGS.scopes)
    try:
        webbrowser.get()
        open_browser = True
    except webbrowser.Error:
        open_browser = False  # headless machine: the URL is written to the MCP log instead
        log.warning("No browser found on this machine; open the sign-in URL from the MCP server log.")
    log.warning("Waiting up to %ss for the Google sign-in to finish.", cfg.SETTINGS.oauth_timeout)
    try:
        # The library print()s the consent URL. stdout is the MCP stdio channel, so send it to
        # stderr (the client's MCP log) instead — useful when the browser can't open.
        with contextlib.redirect_stdout(sys.stderr):
            creds = flow.run_local_server(
                port=cfg.SETTINGS.oauth_port,
                open_browser=open_browser,
                authorization_prompt_message="[sam-gsc-mcp] If no browser opened, visit this URL to sign in: {url}",
                success_message=(
                    "Sam GSC MCP is connected to Google Search Console. You can close this tab "
                    "and return to your AI assistant."
                ),
                timeout_seconds=cfg.SETTINGS.oauth_timeout,
                prompt="consent",
                access_type="offline",
            )
    except Exception as exc:
        if "Timed out" in str(exc) or exc.__class__.__name__ == "WSGITimeoutError":
            raise AuthError(
                f"The Google sign-in page was not completed within {cfg.SETTINGS.oauth_timeout}s. "
                "Call `reauthenticate` to try again (raise GSC_OAUTH_TIMEOUT if you need longer)."
            ) from exc
        if "access_denied" in str(exc):
            raise AuthError(
                "Google blocked the sign-in (access_denied). In Google Cloud Console > Google Auth Platform > "
                "Audience, add your Gmail address as a Test user (or publish the app), then try again."
            ) from exc
        raise
    if creds is None:
        raise AuthError("The Google sign-in did not return credentials. Call `reauthenticate` to try again.")
    _save_token(creds)
    return creds


def _oauth_credentials(allow_browser: bool = True):
    from google.auth.transport.requests import Request

    creds = _load_token()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            return creds
        except Exception as exc:
            log.warning("OAuth token refresh failed (%s); a new sign-in is needed.", exc)
            try:
                cfg.SETTINGS.token_file.unlink()
            except OSError:
                pass
    secrets = _first_existing(cfg.SETTINGS.possible_client_secret_paths())
    if not secrets:
        raise AuthError("OAuth client secrets file not found.")
    kind, _ = inspect_credentials_file(secrets)
    if kind != "oauth_client":
        raise AuthError(
            f"{secrets} is not an OAuth client file (detected: {kind}). Download the JSON for a "
            "'Desktop app' OAuth client from Google Cloud Console > APIs & Services > Credentials."
        )
    if not allow_browser:
        raise AuthError("No cached OAuth token yet. Call `reauthenticate` to sign in.")
    return run_oauth_flow(secrets)


# --------------------------------------------------------------------------- others

def _service_account_credentials():
    from google.oauth2 import service_account

    path = _first_existing(cfg.SETTINGS.possible_service_account_paths())
    if not path:
        raise AuthError("Service account key file not found.")
    kind, detail = inspect_credentials_file(path)
    if kind != "service_account":
        raise AuthError(f"{path} is not a service account key (detected: {kind} {detail or ''}).")
    return service_account.Credentials.from_service_account_file(path, scopes=cfg.SETTINGS.scopes)


def _adc_credentials():
    import google.auth

    creds, _project = google.auth.default(scopes=cfg.SETTINGS.scopes)
    return creds


def _fail_fast_on_bad_paths() -> None:
    s = cfg.SETTINGS
    if s.credentials_path and not os.path.isfile(s.credentials_path):
        raise AuthError(
            f"GSC_CREDENTIALS_PATH is set to {s.credentials_path!r} but that file does not exist. "
            "Use the ABSOLUTE path to your service account JSON key (uvx runs the server from an "
            "internal cache, so relative paths never work)."
        )
    if s.oauth_client_secrets_explicit and s.oauth_client_secrets_file and not os.path.isfile(
        s.oauth_client_secrets_file
    ):
        raise AuthError(
            f"GSC_OAUTH_CLIENT_SECRETS_FILE is set to {s.oauth_client_secrets_file!r} but that file "
            "does not exist. Use the ABSOLUTE path to your OAuth client JSON."
        )


def get_credentials(allow_browser: bool = True):
    """Return cached or new Google credentials, trying methods per GSC_AUTH_MODE."""
    with _LOCK:
        creds = _CACHED.get("creds")
        if creds is not None and getattr(creds, "valid", False):
            return creds

        _fail_fast_on_bad_paths()
        mode = cfg.SETTINGS.auth_mode
        order = {
            "auto": ["oauth", "service_account", "adc"],
            "oauth": ["oauth"],
            "service_account": ["service_account"],
            "adc": ["adc"],
        }[mode]

        errors: list[str] = []
        for method in order:
            try:
                if method == "oauth":
                    # In auto mode only use OAuth when it is configured or already signed in,
                    # so a service-account setup never pops a browser window.
                    has_token = cfg.SETTINGS.token_file.exists()
                    has_secrets = _first_existing(cfg.SETTINGS.possible_client_secret_paths())
                    if mode == "auto" and not (has_token or has_secrets):
                        continue
                    creds = _oauth_credentials(allow_browser=allow_browser)
                elif method == "service_account":
                    if mode == "auto" and not _first_existing(cfg.SETTINGS.possible_service_account_paths()):
                        continue
                    creds = _service_account_credentials()
                else:
                    if mode == "auto" and not (cfg._bool(os.environ.get("GSC_USE_ADC")) or _adc_file_exists()):
                        continue
                    creds = _adc_credentials()
                _CACHED["creds"] = creds
                _CACHED["method"] = method
                return creds
            except AuthError as exc:
                errors.append(f"{method}: {exc}")
            except Exception as exc:
                errors.append(f"{method}: {exc.__class__.__name__}: {exc}")

        raise AuthError(_no_auth_message(errors))


def _adc_file_exists() -> bool:
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".config", "gcloud", "application_default_credentials.json"),
        os.path.join(os.environ.get("APPDATA", ""), "gcloud", "application_default_credentials.json"),
    ]
    return any(os.path.isfile(c) for c in candidates if c)


def _no_auth_message(errors: list[str]) -> str:
    lines = ["Not authenticated with Google Search Console yet."]
    if errors:
        lines.append("Tried: " + " | ".join(errors))
    lines += [
        "Fix it one of these ways:",
        "1) OAuth (your Google account): set GSC_OAUTH_CLIENT_SECRETS_FILE to the ABSOLUTE path of "
        "your 'Desktop app' OAuth client JSON, restart the client, then call `reauthenticate`.",
        "2) Service account: set GSC_CREDENTIALS_PATH to the ABSOLUTE path of the JSON key and add "
        "the service account email as a user in Search Console > Settings > Users and permissions.",
        "3) Or call `setup_gsc_access` and pass the file path — it applies it right away without a restart.",
    ]
    return "\n".join(lines)


def build_service(api: str = "searchconsole", version: str = "v1", allow_browser: bool = True):
    """Build a Google API client. One per call keeps httplib2 thread-safe."""
    from googleapiclient.discovery import build

    creds = get_credentials(allow_browser=allow_browser)
    return build(api, version, credentials=creds, cache_discovery=False)


def logout() -> bool:
    """Delete the cached OAuth token. Returns True if a token was removed."""
    reset_cache()
    token = cfg.SETTINGS.token_file
    if token.exists():
        token.unlink()
        return True
    return False
