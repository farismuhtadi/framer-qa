#!/usr/bin/env python3
"""
qa_agent.py — Framer QA Agent entry point.

Usage:
    python qa_agent.py                    # uses config.json in same folder
    python qa_agent.py --config my.json  # use a custom config file
    python qa_agent.py --list-frames      # print all Figma frames (to help map node IDs)
    python qa_agent.py --seo-only         # skip visual comparison, run SEO checks only
    python qa_agent.py --url /about       # check a single page by path

Edit config.json before running. See README.md for full instructions.
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime
from urllib.parse import urljoin, urlparse


# ── Config Loading ─────────────────────────────────────────────────────────────

def load_config(path: str) -> dict:
    if not os.path.exists(path):
        print(f"❌ Config file not found: {path}")
        print("   Copy config.json and fill in your site URL and Figma details.")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        raw = f.read()

    # Strip comment keys before parsing (keys starting with _comment)
    import re
    raw = re.sub(r'"_comment[^"]*"\s*:\s*"[^"]*",?\s*', '', raw)
    raw = re.sub(r',\s*}', '}', raw)
    raw = re.sub(r',\s*]', ']', raw)

    config = json.loads(raw)

    # Validate required fields
    site_url = config.get("site_url", "")
    if not site_url or "your-site" in site_url:
        print("❌ Please set 'site_url' in config.json before running.")
        sys.exit(1)

    # Default viewports if not set
    if "viewports" not in config:
        config["viewports"] = [
            {"name": "Desktop", "width": 1440, "height": 900},
            {"name": "Tablet",  "width": 768,  "height": 1024},
            {"name": "Mobile",  "width": 375,  "height": 812},
        ]

    config["timeout_ms"] = config.get("timeout_ms", 15000)
    config["diff_threshold"] = config.get("diff_threshold", 10)
    config["output_dir"] = config.get("output_dir", "reports")

    return config


# ── Helpers ────────────────────────────────────────────────────────────────────

def page_path(url: str, site_url: str) -> str:
    """Returns the path component of a URL relative to the site root."""
    site_url = site_url.rstrip("/")
    path = url.replace(site_url, "").strip()
    return path or "/"


def safe_name(path: str) -> str:
    """Converts a URL path to a filesystem-safe name."""
    return path.strip("/").replace("/", "_") or "home"


# ── Main ───────────────────────────────────────────────────────────────────────

async def run(config: dict, seo_only: bool = False, single_url: str = None):
    from modules.crawler     import get_pages_from_sitemap
    from modules.screenshots import ScreenshotTaker
    from modules.figma       import FigmaClient
    from modules.comparator  import compare_images
    from modules.reporter    import generate_report

    site_url   = config["site_url"].rstrip("/")
    viewports  = config["viewports"]
    figma_cfg  = config.get("figma", {})
    has_figma  = (
        not seo_only
        and figma_cfg.get("api_token", "").upper() not in ("", "YOUR_FIGMA_API_TOKEN")
        and figma_cfg.get("file_id",   "").upper() not in ("", "YOUR_FIGMA_FILE_ID")
    )

    # ── Output directory ────────────────────────────────────────────────────────
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = os.path.join(config["output_dir"], timestamp)
    shots_dir  = os.path.join(output_dir, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)

    print(f"\n{'═'*60}")
    print(f"  🔍  Framer QA Agent")
    print(f"  Site: {site_url}")
    print(f"  Figma comparison: {'✅ enabled' if has_figma else '⏭  skipped (not configured)'}")
    print(f"  Viewports: {', '.join(v['name'] for v in viewports)}")
    print(f"{'═'*60}\n")

    # ── Discover pages ───────────────────────────────────────────────────────────
    if single_url:
        # Normalize the single URL
        if single_url.startswith("http"):
            pages = [single_url]
        else:
            pages = [site_url + "/" + single_url.lstrip("/")]
        print(f"📄 Single-page mode: {pages[0]}\n")
    else:
        print("🗺  Discovering pages from sitemap...")
        pages = get_pages_from_sitemap(site_url)
        print(f"   Found {len(pages)} page(s)\n")

    # ── Figma client ─────────────────────────────────────────────────────────────
    figma_client = None
    if has_figma:
        figma_client = FigmaClient(figma_cfg["api_token"], figma_cfg["file_id"])

    # ── Run checks ───────────────────────────────────────────────────────────────
    results = []

    async with ScreenshotTaker(viewports, config["timeout_ms"]) as taker:
        for page_url in pages:
            path = page_path(page_url, site_url)
            print(f"{'─'*60}")
            print(f"📄 {path}  ({page_url})")

            # SEO checks
            print("   🔎 Running SEO checks...")
            try:
                seo = await taker.check_seo(page_url)
                status_line = (
                    f"   ✅ {seo['pass_count']} pass  "
                    f"⚠️  {seo['warn_count']} warn  "
                    f"❌ {seo['fail_count']} fail"
                )
                print(status_line)
            except Exception as e:
                print(f"   ⚠️  SEO check failed: {e}")
                seo = {"url": page_url, "raw": {}, "checks": [], "pass_count": 0, "warn_count": 0, "fail_count": 1}

            # Screenshots + visual comparison
            vp_results = []
            for vp in viewports:
                print(f"   📸 Screenshot: {vp['name']} ({vp['width']}×{vp['height']})...")

                # Take live screenshot
                live_bytes = None
                live_path  = None
                try:
                    live_bytes = await taker.take_screenshot(page_url, vp)
                    live_path  = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_live.png")
                    with open(live_path, "wb") as f:
                        f.write(live_bytes)
                except Exception as e:
                    print(f"   ⚠️  Screenshot failed: {e}")

                # Figma comparison
                figma_path = None
                diff_path  = None
                similarity = None

                if has_figma and live_path:
                    node_id = figma_cfg.get("page_frames", {}).get(path)
                    if node_id:
                        print(f"   🎨 Fetching Figma frame {node_id}...")
                        try:
                            figma_bytes = figma_client.export_frame(node_id, vp["width"])
                            if figma_bytes:
                                figma_path = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_figma.png")
                                with open(figma_path, "wb") as f:
                                    f.write(figma_bytes)

                                diff_path = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_diff.png")
                                similarity = compare_images(
                                    live_path, figma_path, diff_path,
                                    threshold=config["diff_threshold"],
                                )
                                print(f"   {'✅' if similarity >= 95 else '⚠️ '} Visual match: {similarity:.1f}%")
                        except Exception as e:
                            print(f"   ⚠️  Figma comparison failed: {e}")
                    else:
                        print(f"   ℹ️  No Figma frame mapped for '{path}' — skipping visual diff")

                vp_results.append({
                    "viewport":   vp,
                    "live_path":  live_path,
                    "figma_path": figma_path,
                    "diff_path":  diff_path,
                    "similarity": similarity,
                })

            results.append({
                "url":       page_url,
                "path":      path,
                "seo":       seo,
                "viewports": vp_results,
            })

    # ── Generate report ───────────────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("📊 Generating HTML report...")
    from modules.reporter import generate_report
    report_path = generate_report(results, config, output_dir, timestamp)
    print(f"✅ Report saved to: {report_path}")
    print(f"   Open it in your browser to view results.\n")

    return report_path


def cmd_list_frames(config: dict):
    """Prints all top-level frames from the Figma file."""
    from modules.figma import FigmaClient
    figma_cfg = config.get("figma", {})
    client = FigmaClient(figma_cfg["api_token"], figma_cfg["file_id"])
    print("\n🎨 Frames in your Figma file:\n")
    frames = client.list_frames()
    if not frames:
        print("   No frames found (check your API token and file ID).")
        return
    for f in frames:
        print(f"   Page: {f['page']:<20}  Frame: {f['name']:<30}  Node ID: {f['node_id']}")
    print(f"\n   Use these node IDs in config.json → figma.page_frames\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Framer QA Agent")
    parser.add_argument("--config",      default="config.json",  help="Path to config file")
    parser.add_argument("--list-frames", action="store_true",     help="List all Figma frames and exit")
    parser.add_argument("--seo-only",    action="store_true",     help="Skip visual comparison")
    parser.add_argument("--url",         default=None,            help="Check a single URL path (e.g. /about)")
    args = parser.parse_args()

    # Resolve config path relative to script location
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config if os.path.isabs(args.config) else os.path.join(script_dir, args.config)

    config = load_config(config_path)

    if args.list_frames:
        cmd_list_frames(config)
        return

    asyncio.run(run(config, seo_only=args.seo_only, single_url=args.url))


if __name__ == "__main__":
    main()
