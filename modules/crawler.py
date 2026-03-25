"""
crawler.py — Discovers all pages from a site's sitemap.xml.
Falls back to homepage-only if no sitemap is found.
"""

import requests
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlparse


def get_pages_from_sitemap(site_url: str) -> list[str]:
    """
    Fetches and parses the sitemap to return a list of page URLs.
    Supports both sitemap index files and regular sitemaps.
    Falls back to [site_url] if sitemap is unavailable.
    """
    site_url = site_url.rstrip("/")
    sitemap_url = f"{site_url}/sitemap.xml"

    print(f"   Fetching sitemap: {sitemap_url}")

    try:
        resp = requests.get(sitemap_url, timeout=10, headers={"User-Agent": "FramerQA/1.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"   ⚠️  Sitemap not found ({e}). Falling back to homepage only.")
        return [site_url + "/"]

    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as e:
        print(f"   ⚠️  Sitemap XML parse error ({e}). Falling back to homepage only.")
        return [site_url + "/"]

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # Sitemap index (references multiple sitemaps)
    sitemap_locs = root.findall("sm:sitemap/sm:loc", ns)
    if sitemap_locs:
        urls = []
        for loc in sitemap_locs:
            sub_url = loc.text.strip()
            print(f"   Found sub-sitemap: {sub_url}")
            urls.extend(_parse_sitemap(sub_url))
        return _filter_urls(urls, site_url)

    # Regular sitemap
    url_locs = root.findall("sm:url/sm:loc", ns)
    if url_locs:
        urls = [loc.text.strip() for loc in url_locs]
        return _filter_urls(urls, site_url)

    print("   ⚠️  No URLs found in sitemap. Falling back to homepage only.")
    return [site_url + "/"]


def _parse_sitemap(sitemap_url: str) -> list[str]:
    """Parses a single sitemap XML and returns its URL list."""
    try:
        resp = requests.get(sitemap_url, timeout=10, headers={"User-Agent": "FramerQA/1.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns)]
    except Exception as e:
        print(f"   ⚠️  Failed to fetch sub-sitemap {sitemap_url}: {e}")
        return []


def _filter_urls(urls: list[str], site_url: str) -> list[str]:
    """
    Keeps only URLs belonging to the target site,
    deduplicates, and sorts them.
    """
    parsed_base = urlparse(site_url)
    filtered = []
    seen = set()

    for url in urls:
        url = url.strip()
        parsed = urlparse(url)
        # Only keep URLs from the same host
        if parsed.netloc == parsed_base.netloc and url not in seen:
            seen.add(url)
            filtered.append(url)

    filtered.sort()
    return filtered
