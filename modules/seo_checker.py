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
    const h1Els = Array.from(document.querySelectorAll('h1'));
    const formEls = Array.from(document.querySelectorAll('form'));
    const forms = formEls.map(f => ({
        action: f.getAttribute('action'),
        method: (f.getAttribute('method') || 'get').toLowerCase(),
        inputCount: f.querySelectorAll('input:not([type="hidden"]), textarea, select').length,
    }));
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
        forms:               forms,
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

    # Robots
    robots = raw.get("robots")
    if robots and ("noindex" in robots.lower() or "nofollow" in robots.lower()):
        checks.append(_check("Robots", "warn", f"Page may be excluded from search: {robots}", robots))
    elif robots:
        checks.append(_check("Robots", "pass", robots, robots))
    else:
        checks.append(_check("Robots", "pass", "Not set (defaults to index, follow)", None))

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

    # Form receiver — only checked when forms are present on the page
    forms = raw.get("forms") or []
    if forms:
        # A form without an action attribute (null) or an empty action likely has no receiver configured.
        # method="dialog" forms are native dialogs and don't need a submission receiver.
        submission_forms = [f for f in forms if f.get("method") != "dialog" and f.get("inputCount", 0) > 0]
        if submission_forms:
            no_action = [f for f in submission_forms if not f.get("action")]
            if no_action:
                count = len(no_action)
                total = len(submission_forms)
                checks.append(_check(
                    "Form Receiver",
                    "warn",
                    f"{count} of {total} form{'s' if total != 1 else ''} {'have' if count != 1 else 'has'} no submission action — set a receiver in Framer's form settings",
                    None,
                ))
            else:
                checks.append(_check(
                    "Form Receiver",
                    "pass",
                    f"{len(submission_forms)} form{'s' if len(submission_forms) != 1 else ''} {'have' if len(submission_forms) != 1 else 'has'} receivers configured",
                    None,
                ))

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
