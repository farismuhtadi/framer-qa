"""
screenshots.py — Takes full-page screenshots using Playwright at
multiple viewport sizes, and runs SEO checks on loaded pages.
"""

import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


class ScreenshotTaker:
    """
    Async context manager that manages a Playwright browser instance.

    Usage:
        async with ScreenshotTaker(viewports, timeout_ms) as taker:
            png_bytes = await taker.take_screenshot(url, viewport)
            seo_data  = await taker.check_seo(url)
    """

    def __init__(self, viewports: list[dict], timeout_ms: int = 15000):
        self.viewports   = viewports
        self.timeout_ms  = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                # ── Memory / container optimisations ──────────────────────────
                # Critical in Docker/Render: Chrome defaults to /dev/shm which
                # is only 64 MB in most containers — causes crashes / OOM.
                "--disable-dev-shm-usage",
                # Reduce renderer process overhead
                "--no-zygote",
                # Skip unnecessary subsystems
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-default-apps",
                "--disable-sync",
                "--no-first-run",
                "--mute-audio",
                "--hide-scrollbars",
                # Limit blink features that consume memory
                "--blink-settings=imagesEnabled=true",
            ],
        )
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ── Screenshot ──────────────────────────────────────────────────────────────

    async def take_screenshot(self, url: str, viewport: dict) -> bytes:
        """
        Navigates to url at the given viewport and returns a full-page PNG.

        viewport: {"name": "Desktop", "width": 1440, "height": 900}
        """
        context = await self._browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            await self._dismiss_overlays(page)
            await asyncio.sleep(0.5)
            png_bytes = await page.screenshot(full_page=True, type="png")
        finally:
            await page.close()
            await context.close()
        return png_bytes

    async def check_seo_and_screenshot(self, url: str, viewport: dict) -> tuple[dict, bytes]:
        """
        Loads a page ONCE and returns both SEO results and a full-page screenshot.
        Reusing the same navigation halves the browser work for the first viewport.

        Returns: (seo_dict, png_bytes)
        """
        from modules.seo_checker import check_seo

        context = await self._browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            seo = await check_seo(page, url)
            await self._dismiss_overlays(page)
            await asyncio.sleep(0.5)
            png_bytes = await page.screenshot(full_page=True, type="png")
        finally:
            await page.close()
            await context.close()
        return seo, png_bytes

    # ── SEO Check ───────────────────────────────────────────────────────────────

    async def check_site_seo(self, url: str) -> dict:
        """
        Loads the homepage once and checks site-level signals:
        language, favicon, social preview (OG tags), Twitter card.
        """
        from modules.seo_checker import check_site_seo

        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            result = await check_site_seo(page, url)
        finally:
            await page.close()
            await context.close()
        return result

    async def check_seo(self, url: str) -> dict:
        """
        Loads a page and checks page-level signals only (no screenshot).
        Used in SEO-only mode.
        """
        from modules.seo_checker import check_seo

        context = await self._browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            result = await check_seo(page, url)
        finally:
            await page.close()
            await context.close()
        return result

    async def extract_styles_at_regions(self, url: str, viewport: dict, regions: list[dict]) -> list[dict]:
        """
        For each changed region found in the diff, navigates to the page,
        locates the DOM element at the region centre via elementFromPoint(),
        and returns its key computed CSS properties.

        Returns a list of annotation dicts:
          {index, selector, tag, text_preview, styles: {…}, region: {x1,y1,x2,y2}}
        """
        if not regions:
            return []

        context = await self._browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            device_scale_factor=1,
        )
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)

            annotations = []
            for r in regions:
                cx, cy = r["cx"], r["cy"]
                result = await page.evaluate(f"""() => {{
                    const el = document.elementFromPoint({cx}, {cy});
                    if (!el || el === document.body || el === document.documentElement) return null;
                    const cs  = window.getComputedStyle(el);
                    const tag = el.tagName.toLowerCase();

                    // Build a short selector: tag + id or first class
                    let sel = tag;
                    if (el.id) sel += '#' + el.id;
                    else if (el.classList.length) sel += '.' + Array.from(el.classList).slice(0, 2).join('.');

                    // Short text preview
                    const text = (el.innerText || '').trim().replace(/\\s+/g, ' ').substring(0, 60);

                    // Only include properties that differ from browser defaults
                    function v(prop) {{ return cs.getPropertyValue(prop).trim(); }}
                    const display = v('display');
                    const isFlex  = display === 'flex' || display === 'inline-flex';
                    const isGrid  = display === 'grid'  || display === 'inline-grid';

                    const styles = {{}};
                    const padding = v('padding');
                    if (padding && padding !== '0px') styles.padding = padding;

                    const margin = v('margin');
                    if (margin && margin !== '0px') styles.margin = margin;

                    const gap = v('gap');
                    if (gap && gap !== 'normal' && gap !== '0px') styles.gap = gap;

                    const fontSize = v('font-size');
                    if (fontSize) styles['font-size'] = fontSize;

                    const fontWeight = v('font-weight');
                    if (fontWeight && fontWeight !== '400') styles['font-weight'] = fontWeight;

                    const lineHeight = v('line-height');
                    if (lineHeight && lineHeight !== 'normal') styles['line-height'] = lineHeight;

                    const letterSpacing = v('letter-spacing');
                    if (letterSpacing && letterSpacing !== 'normal' && letterSpacing !== '0px') styles['letter-spacing'] = letterSpacing;

                    const color = v('color');
                    if (color) styles.color = color;

                    const bg = v('background-color');
                    if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') styles['background-color'] = bg;

                    const radius = v('border-radius');
                    if (radius && radius !== '0px') styles['border-radius'] = radius;

                    if (isFlex || isGrid) {{
                        styles.display = display;
                        const dir = v('flex-direction');
                        if (dir && dir !== 'row') styles['flex-direction'] = dir;
                        const align = v('align-items');
                        if (align && align !== 'normal') styles['align-items'] = align;
                        const justify = v('justify-content');
                        if (justify && justify !== 'normal') styles['justify-content'] = justify;
                    }}

                    return {{ selector: sel, tag, text, styles }};
                }}""")

                if result and result.get("styles"):
                    annotations.append({
                        "index":    r["index"],
                        "region":   {"x1": r["x1"], "y1": r["y1"], "x2": r["x2"], "y2": r["y2"]},
                        "selector": result["selector"],
                        "tag":      result["tag"],
                        "text":     result.get("text") or "",
                        "styles":   result["styles"],
                    })
        finally:
            await page.close()
            await context.close()

        return annotations

    # ── Helpers ─────────────────────────────────────────────────────────────────

    async def _dismiss_overlays(self, page: Page):
        """
        Attempts to close common cookie banners / GDPR modals
        so they don't appear in screenshots.
        """
        selectors = [
            "button[id*='accept']",
            "button[class*='accept']",
            "button[class*='cookie']",
            "button[aria-label*='Accept']",
            "[data-testid*='cookie-accept']",
            ".cookie-banner button",
            "#cookie-consent button",
        ]
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=500):
                    await btn.click(timeout=500)
                    await asyncio.sleep(0.3)
                    break
            except Exception:
                pass
