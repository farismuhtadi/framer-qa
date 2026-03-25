"""
seo_checker.py — SEO/meta checks split into site-level and page-level.

Site-level (run once per domain):
  - html[lang]              — language attribute
  - Favicon                 — <link rel="icon"> present and reachable
  - Social preview (OG)     — og:title, og:description, og:image
  - Twitter Card

Page-level (run per page):
  - Meta title              — present, reasonable length
  - Meta description        — present, reasonable length
  - Canonical URL
  - Robots meta
"""

import requests
from playwright.async_api import Page


TITLE_MIN = 10
TITLE_MAX = 60
DESC_MIN  = 50
DESC_MAX  = 160


# ── Shared JS extractor ───────────────────────────────────────────────────────

_EXTRACT_JS = """() => {
    const get = (selector, attr = 'content') => {
        const el = document.querySelector(selector);
        return el ? (attr === 'text' ? el.innerText.trim() : el.getAttribute(attr)) : null;
    };
    const faviconEl =
        document.querySelector('link[rel="icon"]') ||
        document.querySelector('link[rel="shortcut icon"]') ||
        document.querySelector('link[rel="apple-touch-icon"]');
    return {
        title:               document.title || null,
        meta_description:    get('meta[name="description"]'),
        lang:                document.documentElement.getAttribute('lang'),
        favicon_href:        faviconEl ? faviconEl.href : null,
        canonical:           get('link[rel="canonical"]', 'href'),
        og_title:            get('meta[property="og:title"]'),
        og_description:      get('meta[property="og:description"]'),
        og_image:            get('meta[property="og:image"]'),
        og_url:              get('meta[property="og:url"]'),
        og_type:             get('meta[property="og:type"]'),
        twitter_card:        get('meta[name="twitter:card"]'),
        twitter_title:       get('meta[name="twitter:title"]'),
        twitter_description: get('meta[name="twitter:description"]'),
        twitter_image:       get('meta[name="twitter:image"]'),
        robots:              get('meta[name="robots"]'),
    };
}"""


# ── Site-level check (run once) ───────────────────────────────────────────────

async def check_site_seo(page: Page, url: str) -> dict:
    """
    Checks site-wide signals that don't change between pages:
    language, favicon, social preview (OG tags), Twitter card.
    """
    raw = await page.evaluate(_EXTRACT_JS)

    favicon_ok = None
    if raw.get("favicon_href"):
        favicon_ok = _is_url_reachable(raw["favicon_href"])

    og_image_ok = None
    if raw.get("og_image"):
        og_image_ok = _is_url_reachable(raw["og_image"])

    checks = _score_site_checks(raw, favicon_ok, og_image_ok)

    return {
        "url":        url,
        "raw":        raw,
        "favicon_ok": favicon_ok,
        "og_image_ok":og_image_ok,
        "checks":     checks,
        "pass_count": sum(1 for c in checks if c["status"] == "pass"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
    }


def _score_site_checks(raw: dict, favicon_ok, og_image_ok) -> list[dict]:
    checks = []

    # Language
    lang = raw.get("lang")
    if not lang:
        checks.append(_check("Language (html[lang])", "fail", "Missing", None))
    else:
        checks.append(_check("Language (html[lang])", "pass", lang, lang))

    # Favicon
    favicon_href = raw.get("favicon_href")
    if not favicon_href:
        checks.append(_check("Favicon", "fail", "No <link rel='icon'> found", None))
    elif favicon_ok is False:
        checks.append(_check("Favicon", "fail", f"URL not reachable: {favicon_href}", favicon_href))
    elif favicon_ok is True:
        checks.append(_check("Favicon", "pass", "Present and reachable", favicon_href))
    else:
        checks.append(_check("Favicon", "warn", "Present but could not verify", favicon_href))

    # OG Title
    og_title = raw.get("og_title")
    if not og_title:
        checks.append(_check("OG Title", "warn", "Missing — social shares won't have a title", None))
    else:
        checks.append(_check("OG Title", "pass", f"{len(og_title)} chars", og_title))

    # OG Description
    og_desc = raw.get("og_description")
    if not og_desc:
        checks.append(_check("OG Description", "warn", "Missing — social shares won't have a description", None))
    else:
        checks.append(_check("OG Description", "pass", f"{len(og_desc)} chars", og_desc))

    # OG Image (Social Preview)
    og_image = raw.get("og_image")
    if not og_image:
        checks.append(_check("OG Image (Social Preview)", "fail", "Missing — no image on social shares", None))
    elif og_image_ok is False:
        checks.append(_check("OG Image (Social Preview)", "fail", f"Not reachable: {og_image}", og_image))
    elif og_image_ok is True:
        checks.append(_check("OG Image (Social Preview)", "pass", "Present and reachable", og_image))
    else:
        checks.append(_check("OG Image (Social Preview)", "warn", "Present but could not verify", og_image))

    # Twitter Card
    twitter_card = raw.get("twitter_card")
    if not twitter_card:
        checks.append(_check("Twitter Card", "warn", "Missing (optional — falls back to OG)", None))
    else:
        checks.append(_check("Twitter Card", "pass", twitter_card, twitter_card))

    return checks


# ── Page-level check (run per page) ──────────────────────────────────────────

async def check_seo(page: Page, url: str) -> dict:
    """
    Checks signals that should be unique per page:
    meta title, meta description, canonical URL, robots.
    """
    raw = await page.evaluate(_EXTRACT_JS)
    checks = _score_page_checks(raw, url)

    return {
        "url":        url,
        "raw":        raw,
        "checks":     checks,
        "pass_count": sum(1 for c in checks if c["status"] == "pass"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
    }


def _score_page_checks(raw: dict, page_url: str) -> list[dict]:
    checks = []

    # Meta Title
    title = raw.get("title")
    if not title:
        checks.append(_check("Meta Title", "fail", "Missing", None))
    elif len(title) < TITLE_MIN:
        checks.append(_check("Meta Title", "warn", f"Too short ({len(title)} chars)", title))
    elif len(title) > TITLE_MAX:
        checks.append(_check("Meta Title", "warn", f"Too long ({len(title)} chars, max {TITLE_MAX})", title))
    else:
        checks.append(_check("Meta Title", "pass", f"{len(title)} chars", title))

    # Meta Description
    desc = raw.get("meta_description")
    if not desc:
        checks.append(_check("Meta Description", "fail", "Missing", None))
    elif len(desc) < DESC_MIN:
        checks.append(_check("Meta Description", "warn", f"Too short ({len(desc)} chars, min {DESC_MIN})", desc))
    elif len(desc) > DESC_MAX:
        checks.append(_check("Meta Description", "warn", f"Too long ({len(desc)} chars, max {DESC_MAX})", desc))
    else:
        checks.append(_check("Meta Description", "pass", f"{len(desc)} chars", desc))

    # Canonical URL
    canonical = raw.get("canonical")
    if not canonical:
        checks.append(_check("Canonical URL", "warn", "Missing (optional but recommended)", None))
    else:
        checks.append(_check("Canonical URL", "pass", canonical, canonical))

    # Robots
    robots = raw.get("robots")
    if robots and ("noindex" in robots.lower() or "nofollow" in robots.lower()):
        checks.append(_check("Robots", "warn", f"Page may be excluded from search: {robots}", robots))
    elif robots:
        checks.append(_check("Robots", "pass", robots, robots))
    else:
        checks.append(_check("Robots", "pass", "Not set (defaults to index, follow)", None))

    return checks


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_url_reachable(url: str) -> bool:
    try:
        r = requests.head(url, timeout=6, allow_redirects=True,
                          headers={"User-Agent": "FramerQA/1.0"})
        return r.status_code < 400
    except Exception:
        return False


def _check(name: str, status: str, detail: str, value) -> dict:
    return {"name": name, "status": status, "detail": detail, "value": value}
