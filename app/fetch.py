"""
Fetch URL and extract page text for web-injection tests.

Vulnerable-by-design: no strict SSRF allowlist; hidden HTML text is included in LLM
context (injection surface). Uses BeautifulSoup for structured extraction; optional
Playwright headless Chromium when WEB_FETCH_JS=true (JS-rendered SPAs).
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None  # type: ignore

_SELF_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

_NOISE_TAGS = ("script", "style", "svg", "iframe", "template", "head")
_HIDDEN_STYLE_RE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0*)?\s*[;\s]|"
    r"font-size\s*:\s*0|max-height\s*:\s*0|width\s*:\s*0|height\s*:\s*0",
    re.IGNORECASE,
)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _validate_http_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _web_fetch_js_enabled() -> bool:
    from core.config import get_web_fetch_js

    return get_web_fetch_js()


def _app_port() -> int:
    from core.config import get_port

    return get_port()


def _is_self_url(url: str) -> bool:
    """True when URL targets this app (localhost/127.0.0.1 on configured PORT)."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _SELF_HOSTS:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return port == _app_port()


def _fetch_in_process(path: str) -> Optional[str]:
    """
    Fetch a same-app route in-process (Flask test client).
    Avoids HTTP loopback deadlock when gunicorn runs with a single worker.
    """
    if not path:
        path = "/"
    try:
        from api.server import app

        with app.test_client() as client:
            response = client.get(path)
            if response.status_code == 200:
                return response.get_data(as_text=True)
    except Exception:
        return None
    return None


def _fetch_evil_file() -> Optional[str]:
    from pathlib import Path

    evil_file = Path(__file__).resolve().parent / "static" / "evil" / "index.html"
    if evil_file.is_file():
        return evil_file.read_text(encoding="utf-8")
    return None


def _fetch_self_html(url: str) -> tuple[str, str, Optional[str]]:
    """In-process fetch for URLs pointing at this app."""
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path.rstrip("/") == "/evil":
        html = _fetch_evil_file()
        if html:
            return html, "local_file", None
    html = _fetch_in_process(path)
    if html:
        return html, "in_process", None
    return "", "", "Same-origin fetch failed (in-process)"


def fetch_url_html(url: str, timeout: int = 10) -> tuple[str, str, Optional[str]]:
    """
    Fetch raw HTML. Returns (html, fetch_backend, error).
    fetch_backend is 'local_file', 'in_process', 'playwright', 'curl_cffi', or '' on failure.
    """
    if not _validate_http_url(url):
        return "", "", "URL must be http or https with a host"

    if _is_self_url(url):
        html, backend, err = _fetch_self_html(url)
        if html:
            return html, backend, None
        if err:
            return "", backend, err

    if _web_fetch_js_enabled():
        html, err = _fetch_with_playwright(url, timeout)
        if html:
            return html, "playwright", None

    if curl_requests is None:
        return "", "", "curl_cffi not installed"

    try:
        response = curl_requests.get(url, timeout=timeout, impersonate="chrome")
        response.raise_for_status()
        return response.text or "", "curl_cffi", None
    except Exception as exc:
        if _is_self_url(url):
            html, backend, err = _fetch_self_html(url)
            if html:
                return html, backend, None
            return "", backend or "in_process", err or str(exc)
        return "", "", str(exc)


def _fetch_with_playwright(url: str, timeout: int) -> tuple[str, Optional[str]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "", "playwright not installed (pip install playwright && playwright install chromium)"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=max(timeout, 5) * 1000)
                return page.content() or "", None
            finally:
                browser.close()
    except Exception as exc:
        return "", str(exc)


def _element_hidden(el) -> bool:
    if el is None or not getattr(el, "name", None):
        return False
    if el.has_attr("hidden"):
        return True
    if (el.get("aria-hidden") or "").lower() == "true":
        return True
    style = (el.get("style") or "").replace(" ", "")
    if _HIDDEN_STYLE_RE.search(style):
        return True
    return False


def _is_in_hidden_subtree(el) -> bool:
    for node in [el, *el.parents]:
        if getattr(node, "name", None) and _element_hidden(node):
            return True
    return False


def _tag_text(el) -> str:
    if el is None:
        return ""
    return _normalize_whitespace(el.get_text(separator=" ", strip=True))


def _main_content_root(soup):
    for selector in ("main", "article", '[role="main"]'):
        found = soup.select_one(selector)
        if found and _tag_text(found):
            return found
    body = soup.body
    if body is not None:
        return body
    return soup


def extract_page_text(html: str, url: str = "") -> Dict[str, Any]:
    """
    Parse HTML with BeautifulSoup. Returns structured fields plus context_text for the LLM.
    Hidden/off-screen HTML text is retained for injection testing.
    """
    try:
        from bs4 import BeautifulSoup, Comment
    except ImportError as exc:
        raise RuntimeError("beautifulsoup4 not installed") from exc

    parser = "lxml"
    try:
        import lxml  # noqa: F401
    except ImportError:
        parser = "html.parser"

    soup = BeautifulSoup(html or "", parser)

    title = _normalize_whitespace(soup.title.get_text(strip=True) if soup.title else "")
    meta_description = ""
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        if name in ("description", "og:description") and meta.get("content"):
            meta_description = _normalize_whitespace(meta["content"])
            break

    noscript_parts: list[str] = []
    for ns in soup.find_all("noscript"):
        text = _tag_text(ns)
        if text:
            noscript_parts.append(text)
        ns.decompose()

    for tag_name in _NOISE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    visible_chunks: list[str] = []
    hidden_chunks: list[str] = []
    for text_node in soup.find_all(string=True):
        if isinstance(text_node, Comment):
            continue
        parent = text_node.parent
        if parent is None or parent.name in _NOISE_TAGS:
            continue
        chunk = _normalize_whitespace(str(text_node))
        if len(chunk) < 2 or chunk.lower() in {"html", "body"}:
            continue
        if parent.name in ("html", "head"):
            continue
        if _is_in_hidden_subtree(parent):
            hidden_chunks.append(chunk)
        else:
            visible_chunks.append(chunk)

    def _dedupe_parts(parts: list[str]) -> str:
        seen: set[str] = set()
        ordered: list[str] = []
        for part in parts:
            key = part.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(part)
        return _normalize_whitespace(" ".join(ordered))

    main_root = _main_content_root(soup)
    main_text = _tag_text(main_root)

    visible_text = _dedupe_parts(visible_chunks)
    hidden_text = _dedupe_parts(hidden_chunks + noscript_parts)

    if not visible_text and main_text:
        visible_text = main_text

    # Full LLM context: structured, includes hidden content (injection surface)
    sections: list[str] = []
    if title:
        sections.append(f"Title: {title}")
    if meta_description:
        sections.append(f"Meta description: {meta_description}")
    if visible_text:
        sections.append(f"Visible page text:\n{visible_text}")
    if hidden_text:
        sections.append(
            "Hidden/off-screen HTML text (included for injection testing):\n" + hidden_text
        )
    if not sections:
        fallback = _strip_html_legacy(html)
        if fallback:
            sections.append(f"Page text:\n{fallback}")

    context_text = "\n\n".join(sections)
    return {
        "url": url,
        "title": title,
        "meta_description": meta_description,
        "visible_text": visible_text,
        "hidden_text": hidden_text,
        "main_text": main_text,
        "context_text": context_text,
        "chars": len(context_text),
        "extractor": "beautifulsoup",
    }


def _strip_html_legacy(html: str) -> str:
    """Regex fallback when BeautifulSoup yields nothing."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_whitespace(text)


def fetch_page_context(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Fetch URL and extract structured page text for web injection.
    Returns dict with context_text, fetch_backend, extraction_ms, warning, etc.
    """
    started = time.perf_counter()
    html, fetch_backend, fetch_error = fetch_url_html(url, timeout=timeout)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if fetch_error and not html:
        return {
            "url": url,
            "context_text": "",
            "title": "",
            "meta_description": "",
            "visible_text": "",
            "hidden_text": "",
            "chars": 0,
            "fetch_backend": fetch_backend or None,
            "extractor": None,
            "fetch_ms": elapsed_ms,
            "extraction_ms": elapsed_ms,
            "warning": f"URL fetch failed: {fetch_error}",
        }

    try:
        extracted = extract_page_text(html, url=url)
    except Exception as exc:
        fallback = _strip_html_legacy(html)
        return {
            "url": url,
            "context_text": fallback,
            "title": "",
            "meta_description": "",
            "visible_text": fallback,
            "hidden_text": "",
            "chars": len(fallback),
            "fetch_backend": fetch_backend,
            "extractor": "regex_fallback",
            "fetch_ms": elapsed_ms,
            "extraction_ms": int((time.perf_counter() - started) * 1000),
            "warning": f"HTML parse fallback: {exc}",
        }

    total_ms = int((time.perf_counter() - started) * 1000)
    warning = None
    if not extracted.get("context_text"):
        warning = "URL fetch returned no extractable text."
    elif extracted.get("hidden_text"):
        warning = (
            "Hidden HTML text was extracted and will be sent to the model — "
            "common indirect injection surface."
        )

    return {
        **extracted,
        "fetch_backend": fetch_backend,
        "fetch_ms": elapsed_ms,
        "extraction_ms": total_ms,
        "warning": warning,
    }


def fetch_url_to_text(url: str, timeout: int = 10) -> str:
    """Backward-compatible: return LLM context text for a URL."""
    return fetch_page_context(url, timeout=timeout).get("context_text") or ""
