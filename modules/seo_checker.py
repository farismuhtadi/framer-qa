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

import re
import requests
from urllib.parse import urlparse, unquote
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
    const h1Els = Array.from(document.querySelectorAll('h1'));
    const origin = location.origin;
    const internalLinks = Array.from(document.querySelectorAll('a[href]'))
        .map(a => {
            try {
                const url = new URL(a.href, location.href);
                if (url.origin === origin && url.pathname !== location.pathname) return url.origin + url.pathname;
                return null;
            } catch { return null; }
        })
        .filter(Boolean);

    // Broken images — fully loaded but zero dimensions
    const brokenImages = Array.from(document.querySelectorAll('img'))
        .filter(img => img.complete && (img.naturalWidth === 0 || img.naturalHeight === 0) && img.src && !img.src.startsWith('data:'))
        .map(img => img.src);

    // Images missing meaningful alt text — catches both missing alt and empty alt=""
    // Skip small images (icons/decorative) under 50px in either dimension
    const imagesWithoutAlt = Array.from(document.querySelectorAll('img'))
        .filter(img => {
            if (!img.src || img.src.startsWith('data:')) return false;
            const hasAlt = img.hasAttribute('alt') && img.getAttribute('alt').trim() !== '';
            if (hasAlt) return false;
            // skip likely decorative/icon images
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            if (w > 0 && w < 50 && h > 0 && h < 50) return false;
            return true;
        })
        .map(img => img.src.split('/').pop().split('?')[0] || img.src)
        .slice(0, 10);

    // Placeholder text — lorem ipsum variants
    const bodyText = (document.body && document.body.innerText) || '';
    const placeholderMatches = [];
    const placeholderPatterns = [
        /lorem\s+ipsum/i,
        /dolor\s+sit\s+amet/i,
        /\[placeholder\]/i,
        /\[your\s+(?:text|content|title|name)\]/i,
        /placeholder\s+text/i,
        /dummy\s+text/i,
        /sample\s+text/i,
    ];
    placeholderPatterns.forEach(re => {
        const m = bodyText.match(re);
        if (m) placeholderMatches.push(m[0]);
    });

    // Page performance timing
    const navEntry = performance.getEntriesByType('navigation')[0];
    const paintEntries = performance.getEntriesByType('paint');
    const fcpEntry = paintEntries.find(p => p.name === 'first-contentful-paint');
    const perf = navEntry ? {
        ttfb:               Math.round(navEntry.responseStart - navEntry.requestStart),
        dom_content_loaded: Math.round(navEntry.domContentLoadedEventEnd - navEntry.startTime),
        load_time:          Math.round(navEntry.loadEventEnd - navEntry.startTime),
        fcp:                fcpEntry ? Math.round(fcpEntry.startTime) : null,
    } : null;

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
        h1_texts:            h1Els.map(el => el.innerText.trim()).filter(Boolean),
        internal_links:      [...new Set(internalLinks)],
        broken_images:       [...new Set(brokenImages)],
        images_without_alt:  [...new Set(imagesWithoutAlt)],
        placeholder_matches: placeholderMatches,
        perf:                perf,
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
        checks.append(_check("Site Language", "fail", "Missing html[lang] attribute", None))
    else:
        checks.append(_check("Site Language", "pass", lang, lang))

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

    # Meta Title (site-level snapshot — same value as og:title in Framer)
    title = raw.get("title")
    if not title:
        checks.append(_check("Meta Title", "fail", "Missing", None))
    elif len(title) < TITLE_MIN:
        checks.append(_check("Meta Title", "warn", f"Too short ({len(title)} chars)", title))
    elif len(title) > TITLE_MAX:
        checks.append(_check("Meta Title", "warn", f"Too long ({len(title)} chars, max {TITLE_MAX})", title))
    else:
        checks.append(_check("Meta Title", "pass", f"{len(title)} chars", title))

    # Meta Description (site-level snapshot — same value as og:description in Framer)
    desc = raw.get("meta_description")
    if not desc:
        checks.append(_check("Meta Description", "fail", "Missing", None))
    elif len(desc) < DESC_MIN:
        checks.append(_check("Meta Description", "warn", f"Too short ({len(desc)} chars, min {DESC_MIN})", desc))
    elif len(desc) > DESC_MAX:
        checks.append(_check("Meta Description", "warn", f"Too long ({len(desc)} chars, max {DESC_MAX})", desc))
    else:
        checks.append(_check("Meta Description", "pass", f"{len(desc)} chars", desc))

    # Social Preview image (og:image — also used by Twitter/X as fallback)
    og_image = raw.get("og_image")
    if not og_image:
        checks.append(_check("Social Preview Image", "fail", "Missing — no image on social shares", None))
    elif og_image_ok is False:
        checks.append(_check("Social Preview Image", "fail", f"Image URL not reachable", og_image))
    elif og_image_ok is True:
        checks.append(_check("Social Preview Image", "pass", "Present and reachable", og_image))
    else:
        checks.append(_check("Social Preview Image", "warn", "Present but could not verify", og_image))

    return checks


# ── Page-level check (run per page) ──────────────────────────────────────────

async def check_seo(page: Page, url: str, console_errors: list = None) -> dict:
    """
    Checks signals that should be unique per page:
    meta title, meta description, canonical URL, robots,
    broken images, placeholder text, and JS console errors.
    """
    raw = await page.evaluate(_EXTRACT_JS)
    checks = _score_page_checks(raw, url, console_errors or [])

    return {
        "url":        url,
        "raw":        raw,
        "checks":     checks,
        "pass_count": sum(1 for c in checks if c["status"] == "pass"),
        "warn_count": sum(1 for c in checks if c["status"] == "warn"),
        "fail_count": sum(1 for c in checks if c["status"] == "fail"),
    }


def _score_page_checks(raw: dict, page_url: str, console_errors: list = None) -> list[dict]:
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

    # H1
    h1_texts = raw.get("h1_texts") or []
    if not h1_texts:
        checks.append(_check("H1 Heading", "fail", "No H1 found on page", None))
    elif len(h1_texts) > 1:
        checks.append(_check("H1 Heading", "warn", f"{len(h1_texts)} H1s found — should have exactly one", " / ".join(h1_texts[:3])))
    else:
        checks.append(_check("H1 Heading", "pass", h1_texts[0][:80], h1_texts[0]))

    # Canonical URL
    canonical = raw.get("canonical")
    if not canonical:
        checks.append(_check("Canonical URL", "warn", "Missing (optional but recommended)", None))
    else:
        checks.append(_check("Canonical URL", "pass", canonical, canonical))

    # URL slug — check for non-ASCII characters (accented, Icelandic, etc.)
    path = urlparse(page_url).path
    decoded_path = unquote(path)
    bad_chars = list(set(re.findall(r'[^\x00-\x7F]', decoded_path)))
    if bad_chars:
        checks.append(_check("URL Slug", "warn",
                             f"Contains special characters: {''.join(bad_chars[:8])} — may cause issues with crawlers and sharing",
                             decoded_path))
    else:
        checks.append(_check("URL Slug", "pass", "No special characters in slug", None))

    # Robots — only surface when something is actually blocking indexing
    robots = raw.get("robots")
    if robots and ("noindex" in robots.lower() or "nofollow" in robots.lower()):
        checks.append(_check("Robots", "warn", f"Page may be excluded from search: {robots}", robots))

    # Broken internal links
    internal_links = raw.get("internal_links") or []
    if internal_links:
        broken = _find_broken_links(internal_links)
        if broken:
            checks.append(_check("Broken Links", "fail",
                                 f"{len(broken)} broken link{'s' if len(broken) != 1 else ''}: {', '.join(broken[:3])}{'…' if len(broken) > 3 else ''}",
                                 "\n".join(broken)))
        else:
            checks.append(_check("Broken Links", "pass", f"{len(internal_links)} internal link{'s' if len(internal_links) != 1 else ''} checked", None))
    else:
        checks.append(_check("Broken Links", "pass", "No internal links found", None))

    # Broken images
    broken_imgs = raw.get("broken_images") or []
    if broken_imgs:
        checks.append(_check("Broken Images", "fail",
                             f"{len(broken_imgs)} broken image{'s' if len(broken_imgs) != 1 else ''}: {', '.join(broken_imgs[:2])}{'…' if len(broken_imgs) > 2 else ''}",
                             "\n".join(broken_imgs)))
    else:
        checks.append(_check("Broken Images", "pass", "All images loaded successfully", None))

    # Image alt text
    missing_alt = raw.get("images_without_alt") or []
    if missing_alt:
        count = len(missing_alt)
        checks.append(_check("Image Alt Text", "warn",
                             f"{count} image{'s' if count != 1 else ''} missing alt text",
                             None))
    else:
        checks.append(_check("Image Alt Text", "pass", "All images have alt text", None))

    # Placeholder content
    placeholders = raw.get("placeholder_matches") or []
    if placeholders:
        checks.append(_check("Placeholder Text", "fail",
                             f"Found placeholder content: {', '.join(set(placeholders))}",
                             ", ".join(set(placeholders))))
    else:
        checks.append(_check("Placeholder Text", "pass", "No placeholder text found", None))

    # Console errors
    errs = [e for e in (console_errors or []) if e]
    if errs:
        preview = errs[0][:80] + ("…" if len(errs[0]) > 80 else "")
        checks.append(_check("Console Errors", "fail",
                             f"{len(errs)} JS error{'s' if len(errs) != 1 else ''}: {preview}",
                             "\n".join(errs[:10])))
    else:
        checks.append(_check("Console Errors", "pass", "No console errors detected", None))

    # Page speed (from Navigation Timing API — measured in the browser)
    perf = raw.get("perf")
    if perf and isinstance(perf, dict):
        load_ms = perf.get("load_time")
        ttfb_ms = perf.get("ttfb")
        fcp_ms  = perf.get("fcp")
        parts   = []

        if load_ms is not None:
            parts.append(f"loaded in {load_ms}ms")
        if fcp_ms is not None:
            parts.append(f"first paint {fcp_ms}ms")
        if ttfb_ms is not None:
            parts.append(f"server {ttfb_ms}ms")
        metrics = " · ".join(parts) if parts else "Measured"

        # Score: fail if load > 5s or TTFB > 1.2s; warn if load > 3s or TTFB > 0.6s
        if (load_ms is not None and load_ms > 5000) or (ttfb_ms is not None and ttfb_ms > 1200):
            detail = f"Slow — {metrics}"
            checks.append(_check("Page Speed", "fail", detail, None))
        elif (load_ms is not None and load_ms > 3000) or (ttfb_ms is not None and ttfb_ms > 600):
            detail = f"Could be faster — {metrics}"
            checks.append(_check("Page Speed", "warn", detail, None))
        else:
            detail = f"Fast — {metrics}"
            checks.append(_check("Page Speed", "pass", detail, None))
    else:
        checks.append(_check("Page Speed", "warn", "Timing data unavailable", None))

    return checks


def _find_broken_links(urls: list[str]) -> list[str]:
    """HEAD-checks a list of URLs and returns those that return 4xx/5xx."""
    import concurrent.futures
    broken = []

    def check(url):
        try:
            r = requests.head(url, timeout=6, allow_redirects=True,
                              headers={"User-Agent": "FramerQA/1.0"})
            if r.status_code >= 400:
                return url
            return None
        except Exception:
            return url  # treat connection errors as broken

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = ex.map(check, urls[:30])  # cap at 30 links per page
    return [u for u in results if u]


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
