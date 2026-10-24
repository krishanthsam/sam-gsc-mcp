"""Shared fixtures: an isolated config dir and a fake Google API client."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolate config before the package is imported anywhere.
os.environ.setdefault("GSC_CONFIG_DIR", str(ROOT / ".pytest-config"))
for var in ("GSC_SITE_URL", "GSC_CREDENTIALS_PATH", "GOOGLE_APPLICATION_CREDENTIALS", "GSC_OAUTH_CLIENT_SECRETS_FILE",
            "GSC_ALLOW_DESTRUCTIVE", "GSC_READ_ONLY", "GSC_TOOLSETS", "GSC_ENABLE_INDEXING_API", "GSC_SKIP_OAUTH"):
    os.environ.pop(var, None)


class _Req:
    def __init__(self, fn):
        self._fn = fn

    def execute(self, num_retries=0):
        return self._fn()


class FakeService:
    """Minimal stand-in for googleapiclient's searchconsole v1 resource tree."""

    def __init__(self, sites=None, query_handler=None, inspect_handler=None, sitemaps=None):
        self.sites_list = sites or [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}]
        self.query_handler = query_handler or (lambda site, body: {"rows": []})
        self.inspect_handler = inspect_handler or (lambda body: {})
        self.sitemap_list = sitemaps or []
        self.calls = []

    # sites()
    def sites(self):
        svc = self

        class Sites:
            def list(self):
                return _Req(lambda: {"siteEntry": svc.sites_list})

            def get(self, siteUrl):
                return _Req(lambda: {"permissionLevel": "siteOwner"})

        return Sites()

    def searchanalytics(self):
        svc = self

        class SA:
            def query(self, siteUrl, body):
                svc.calls.append(("query", siteUrl, json.loads(json.dumps(body))))
                return _Req(lambda: svc.query_handler(siteUrl, body))

        return SA()

    def urlInspection(self):
        svc = self

        class Index:
            def inspect(self, body):
                svc.calls.append(("inspect", body))
                return _Req(lambda: svc.inspect_handler(body))

        class UI:
            def index(self):
                return Index()

        return UI()

    def sitemaps(self):
        svc = self

        class SM:
            def list(self, siteUrl, sitemapIndex=None):
                return _Req(lambda: {"sitemap": svc.sitemap_list})

            def get(self, siteUrl, feedpath):
                return _Req(lambda: next((s for s in svc.sitemap_list if s["path"] == feedpath), {}))

            def submit(self, siteUrl, feedpath):
                svc.calls.append(("submit", feedpath))
                return _Req(lambda: {})

            def delete(self, siteUrl, feedpath):
                svc.calls.append(("delete", feedpath))
                return _Req(lambda: {})

        return SM()


@pytest.fixture
def fake(monkeypatch):
    from sam_gsc_mcp import auth, gsc

    svc = FakeService()
    monkeypatch.setattr(gsc, "service", lambda *a, **k: svc)
    monkeypatch.setattr(auth, "get_credentials", lambda *a, **k: object())
    gsc.clear_site_cache()
    yield svc
    gsc.clear_site_cache()


def parse(result):
    """Normalise call_tool output across MCP SDK 1.x and 2.x to a dict."""
    content = getattr(result, "content", None)
    if content is None:
        content = result[0] if isinstance(result, tuple) else result
    text = content[0].text
    return json.loads(text)
