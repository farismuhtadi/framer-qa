"""
seo_checker.py — Extracts and validates all SEO/meta signals from a page.

Checks per page:
  - Meta title (present, non-empty, reasonable length)
  - Meta description (present, non-empty, reasonable length)
  - Site language (html[lang] attribute)
  - Favicon (link[rel=icon] present and reachable)
  - Social preview: og:title, og:description, og:image, twitter:card
  - Canonical URL
"""

import requests
from playwright.async_api import Page


# Recommended character limits
TITLE_MIN = 10
TITLE_MAX = 60
DESC_MIN  = 50
DESC_MAX  = 160


async def check_seo(page: Page, url: str) -> dict:
    """
    Runs all SEO checks on an already-loaded Playwright page.
    Returns a structured dict of results.
    """
    result = await page.evaluate("""() => {
        const get = (selector, attr = 'content') => {
            const el = document.querySelector(selector);
            return el ? (attr === 'text' ? el.innerText.trim() : el.getAttribute(attr)) : null;
        };

        // Favicon: check multiple common patterns
        const faviconEl =
            document.querySelector('link[rel="icon"]') ||
            document.querySelector('link[rel="shortcut icon"]') ||
            document.querySelector('link[rel="apple-touch-icon"]');

        const faviconHref = faviconEl ? faviconEl.href : null;

        return {
            title:              document.title || null,
            meta_description:   get('meta[name="description"]'),
            lang:               document.documentElement.getAttribute('lang'),
            favicon_href:       faviconHref,
            canonical:          get('link[rel="canonical"]', 'href'),

            // Open Graph
            og_title:           get('meta[property="og:title"]'),
            og_description:     get('meta[property="og:description"]'),
            og_image:           get('meta[property="og:image"]'),
            og_url:             get('meta[property="og:url"]'),
            og_type:            get('meta[property="og:type"]'),

            // Twitter Card
            twitter_card:       get('meta[name="twitter:card"]'),
            twitter_title:      get('meta[name="twitter:title"]'),
            twitter_description: get('meta[name="twitter:description"]'),
            twitter_image:      get('meta[name="twitter:image"]'),

            // Robots
            robots:             get('meta[name="robots"]'),
        };
    }""")

    # Verify favicon is reachable (HTTP HEAD request)
    favicon_ok = None
    if result.get("favicon_href"):
        favicon_ok = _is_url_reachable(result["favicon_href"])

    # Verify OG image is reachable
    og_image_ok = None
    if result.get("og_image"):
        og_image_ok = _is_url_reachable(result["og_image"])

    # Score each check
    checks = _score_checks(result, favicon_ok, og_image_ok, url)

    return {
        "url":          url,
        "raw":          result,
        "favicon_ok":   favicon_ok,
        "og_image_ok":  og_image_ok,
        "checks":       checks,
        "pass_count":   sum(1 for c in checks if c["status"] == "pass"),
        "warn_count":   sum(1 for c in checks if c["status"] == "warn"),
        "fail_count":   sum(1 for c in checks if c["status"] == "fail"),
    }


def _is_url_reachable(url: str) -> bool:
    """Returns True if a HEAD request to the URL succeeds."""
    try:
        r = requests.head(url, timeout=6, allow_redirects=True,
                          headers={"User-Agent": "FramerQA/1.0"})
        return r.status_code < 400
    except Exception:
        return False


def _score_checks(raw: dict, favicon_ok, og_image_ok, page_url: str) -> list[dict]:
    """Returns a list of check result dicts with status: pass | warn | fail."""
    checks = []

    # ── Meta Title ──────────────────────────────────────────────────────────────
    title = raw.get("title")
    if not title:
        checks.append(_check("Meta Title", "fail", "Missing", None))
    elif len(title) < TITLE_MIN:
        checks.append(_check("Meta Title", "warn", f"Too short ({len(title)} chars)", title))
    elif len(title) > TITLE_MAX:
        checks.append(_check("Meta Title", "warn", f"Too long ({len(title)} chars, max {TITLE_MAX})", title))
    else:
        checks.append(_check("Meta Title", "pass", f"{len(title)} chars", title))

    # ── Meta Description ─────────────────────────────────────────────────────────
    desc = raw.get("meta_description")
    if not desc:
        checks.append(_check("Meta Description", "fail", "Missing", None))
    elif len(desc) < DESC_MIN:
        checks.append(_check("Meta Description", "warn", f"Too short ({len(desc)} chars, min {DESC_MIN})", desc))
    elif len(desc) > DESC_MAX:
        checks.append(_check("Meta Description", "warn", f"Too long ({len(desc)} chars, max {DESC_MAX})", desc))
    else:
        checks.append(_check("Meta Description", "pass", f"{len(desc)} chars", desc))

    # ── Site Language ────────────────────────────────────────────────────────────
    lang = raw.get("lang")
    if not lang:
        checks.append(_check("Language (html[lang])", "fail", "Missing", None))
    else:
        checks.append(_check("Language (html[lang])", "pass", lang, lang))

    # ── Favicon ──────────────────────────────────────────────────────────────────
    favicon_href = raw.get("favicon_href")
    if not favicon_href:
        checks.append(_check("Favicon", "fail", "No <link rel='icon'> found", None))
    elif favicon_ok is False:
        checks.append(_check("Favicon", "fail", f"URL not reachable: {favicon_href}", favicon_href))
    elif favicon_ok is True:
        checks.append(_check("Favicon", "pass", "Present and reachable", favicon_href))
    else:
        checks.append(_check("Favicon", "warn", "Present but could not verify", favicon_href))

    # ── Canonical URL ────────────────────────────────────────────────────────────
    canonical = raw.get("canonical")
    if not canonical:
        checks.append(_check("Canonical URL", "warn", "Missing (optional but recommended)", None))
    else:
        checks.append(_check("Canonical URL", "pass", canonical, canonical))

    # ── OG Title ─────────────────────────────────────────────────────────────────
    og_title = raw.get("og_title")
    if not og_title:
        checks.append(_check("OG Title", "warn", "Missing — social shares won't have a title", None))
    else:
        checks.append(_check("OG Title", "pass", f"{len(og_title)} chars", og_title))

    # ── OG Description ───────────────────────────────────────────────────────────
    og_desc = raw.get("og_description")
    if not og_desc:
        checks.append(_check("OG Description", "warn", "Missing — social shares won't have a description", None))
    else:
        checks.append(_check("OG Description", "pass", f"{len(og_desc)} chars", og_desc))

    # ── OG Image (Social Preview) ─────────────────────────────────────────────────
    og_image = raw.get("og_image")
    if not og_image:
        checks.append(_check("OG Image (Social Preview)", "fail", "Missing — no image will show on social shares", None))
    elif og_image_ok is False:
        checks.append(_check("OG Image (Social Preview)", "fail", f"Image URL not reachable: {og_image}", og_image))
    elif og_image_ok is True:
        checks.append(_check("OG Image (Social Preview)", "pass", "Present and reachable", og_image))
    else:
        checks.append(_check("OG Image (Social Preview)", "warn", "Present but could not verify", og_image))

    # ── Twitter Card ─────────────────────────────────────────────────────────────
    twitter_card = raw.get("twitter_card")
    if not twitter_card:
        checks.append(_check("Twitter Card", "warn", "Missing (optional — falls back to OG tags)", None))
    else:
        checks.append(_check("Twitter Card", "pass", twitter_card, twitter_card))

    # ── Robots ───────────────────────────────────────────────────────────────────
    robots = raw.get("robots")
    if robots and ("noindex" in robots.lower() or "nofollow" in robots.lower()):
        checks.append(_check("Robots", "warn", f"Page may be excluded from search: {robots}", robots))
    elif robots:
        checks.append(_check("Robots", "pass", robots, robots))
    else:
        checks.append(_check("Robots", "pass", "Not set (defaults to index, follow)", None))

    return checks


def _check(name: str, status: str, detail: str, value) -> dict:
    return {"name": name, "status": status, "detail": detail, "value": value}
