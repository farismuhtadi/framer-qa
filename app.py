#!/usr/bin/env python3
"""
app.py — Framer QA Web Server

Run with:
    python app.py                   # dev mode (port 5000)
    python app.py --port 8080       # custom port
    gunicorn -w 2 -b 0.0.0.0:8080 "app:app"  # production

Environment variables:
    PORT          Server port (default: 5000)
    SECRET_KEY    Flask secret key (required in production)
    MAX_JOBS      Max concurrent jobs (default: 3)
    JOB_TTL_HOURS Keep reports for N hours (default: 24)
"""

import asyncio
import builtins
import json
import os
import re
import shutil
import sys
import threading
import time
import uuid
import argparse
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, abort

# ── App setup ──────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-key-change-in-prod")

MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_JOBS", 3))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_HOURS", 24)) * 3600
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── Print capture (thread-local routing) ──────────────────────────────────────

_orig_print = builtins.print
_tlocal = threading.local()
_jobs: dict[str, "Job"] = {}
_jobs_lock = threading.Lock()


def _patched_print(*args, **kwargs):
    """Routes print() calls to the current job's log buffer."""
    msg = " ".join(str(a) for a in args)
    job_id = getattr(_tlocal, "job_id", None)
    if job_id:
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job:
            job.append_log(msg)
    _orig_print(*args, **kwargs)


builtins.print = _patched_print

# ── Job model ─────────────────────────────────────────────────────────────────


class Job:
    def __init__(self, job_id: str, config: dict):
        self.id = job_id
        self.config = config
        self.status = "queued"       # queued | running | done | error
        self.logs: list[str] = []
        self.progress = 0.0          # 0.0 – 1.0
        self.report_url: str | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self._lock = threading.Lock()

    def append_log(self, msg: str):
        with self._lock:
            self.logs.append(msg)
            # Infer rough progress from log content
            self._update_progress(msg)

    def _update_progress(self, msg: str):
        """Heuristically updates progress from log messages."""
        if "Discovering pages" in msg:
            self.progress = 0.05
        elif "Running SEO checks" in msg:
            self.progress = min(self.progress + 0.08, 0.85)
        elif "Screenshot:" in msg:
            self.progress = min(self.progress + 0.05, 0.90)
        elif "Fetching Figma" in msg:
            self.progress = min(self.progress + 0.04, 0.92)
        elif "Visual match" in msg:
            self.progress = min(self.progress + 0.03, 0.95)
        elif "Generating HTML report" in msg:
            self.progress = 0.97

    def to_dict(self, include_logs_from: int = 0) -> dict:
        with self._lock:
            return {
                "id":          self.id,
                "status":      self.status,
                "progress":    round(self.progress, 3),
                "logs":        self.logs[include_logs_from:],
                "log_count":   len(self.logs),
                "report_url":  self.report_url,
                "error":       self.error,
                "created_at":  self.created_at,
            }


# ── Job runner ────────────────────────────────────────────────────────────────

def _running_job_count() -> int:
    with _jobs_lock:
        return sum(1 for j in _jobs.values() if j.status == "running")


def _thread_run_job(job_id: str):
    """Entry point for the background job thread."""
    _tlocal.job_id = job_id

    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return

    job.status = "running"
    job.progress = 0.02

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        report_path = loop.run_until_complete(_run_qa(job))
        job.status = "done"
        job.progress = 1.0
        if report_path:
            # Make URL relative to /reports/<job_id>/report.html
            job.report_url = f"/reports/{job_id}/report.html"
    except Exception as exc:
        job.status = "error"
        job.error = str(exc)
        job.append_log(f"❌ Fatal error: {exc}")
        import traceback
        _orig_print(f"[Job {job_id}] Error: {traceback.format_exc()}")
    finally:
        loop.close()
        _tlocal.job_id = None


async def _run_qa(job: "Job") -> str | None:
    """Core async QA runner — uses the existing modules."""
    # Import here so print-patching is active for all module-level prints
    from modules.crawler     import get_pages_from_sitemap
    from modules.screenshots import ScreenshotTaker
    from modules.figma       import FigmaClient
    from modules.comparator  import compare_images
    from modules.reporter    import generate_report

    config    = job.config
    site_url  = config["site_url"].rstrip("/")
    viewports = config["viewports"]
    figma_cfg = config.get("figma", {})
    has_figma = bool(
        figma_cfg.get("api_token")
        and figma_cfg.get("file_id")
        and any(figma_cfg.get("page_frames", {}).values())
    )

    # Output dirs
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = os.path.join(REPORTS_DIR, job.id)
    shots_dir  = os.path.join(output_dir, "screenshots")
    os.makedirs(shots_dir, exist_ok=True)

    print(f"{'═'*55}")
    print(f"  Framer QA — {site_url}")
    print(f"  Figma: {'enabled' if has_figma else 'skipped'}")
    print(f"  Viewports: {', '.join(v['name'] for v in viewports)}")
    print(f"{'═'*55}")

    # Discover pages
    print("\n🗺  Discovering pages from sitemap...")
    pages = get_pages_from_sitemap(site_url)
    print(f"   Found {len(pages)} page(s)")

    # Site-level SEO — run once on the homepage
    site_seo = None
    async with ScreenshotTaker(viewports, config.get("timeout_ms", 15000)) as site_taker:
        print("\n🌐 Checking site-level SEO (language, favicon, social preview)...")
        try:
            site_seo = await site_taker.check_site_seo(site_url)
            p, w, f = site_seo["pass_count"], site_seo["warn_count"], site_seo["fail_count"]
            print(f"   ✅ {p} pass  ⚠️  {w} warn  ❌ {f} fail")
        except Exception as e:
            print(f"   ⚠️  Site SEO check failed: {e}")

    # Helpers
    def page_path(url):
        p = url.replace(site_url, "").strip().rstrip("/")
        return p or "/"

    def safe_name(path):
        return path.strip("/").replace("/", "_") or "home"

    figma_client = FigmaClient(figma_cfg["api_token"], figma_cfg["file_id"]) if has_figma else None

    results = []
    total = len(pages)

    async with ScreenshotTaker(viewports, config.get("timeout_ms", 15000)) as taker:
        for idx, page_url in enumerate(pages):
            path = page_path(page_url)
            print(f"\n{'─'*55}")
            print(f"📄 [{idx+1}/{total}] {path}")
            job.progress = 0.05 + (idx / total) * 0.88

            # SEO
            print("   🔎 Running SEO checks...")
            try:
                seo = await taker.check_seo(page_url)
                print(f"   ✅ {seo['pass_count']} pass  ⚠️  {seo['warn_count']} warn  ❌ {seo['fail_count']} fail")
            except Exception as e:
                print(f"   ⚠️  SEO check failed: {e}")
                seo = {"url": page_url, "raw": {}, "checks": [], "pass_count": 0, "warn_count": 0, "fail_count": 1}

            vp_results = []
            for vp in viewports:
                print(f"   📸 Screenshot: {vp['name']} ({vp['width']}px)...")
                live_path = None
                try:
                    live_bytes = await taker.take_screenshot(page_url, vp)
                    live_path  = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_live.png")
                    with open(live_path, "wb") as f:
                        f.write(live_bytes)
                except Exception as e:
                    print(f"   ⚠️  Screenshot failed: {e}")

                figma_path = diff_path = None
                similarity = None

                if has_figma and live_path:
                    frames_for_page = figma_cfg["page_frames"].get(path, {})
                    node_id = frames_for_page.get(vp["name"])
                    if node_id:
                        print(f"   🎨 Fetching Figma frame {node_id}...")
                        try:
                            figma_bytes = figma_client.export_frame(node_id, vp["width"])
                            if figma_bytes:
                                figma_path = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_figma.png")
                                diff_path  = os.path.join(shots_dir, f"{safe_name(path)}_{vp['name'].lower()}_diff.png")
                                with open(figma_path, "wb") as f:
                                    f.write(figma_bytes)
                                similarity = compare_images(
                                    live_path, figma_path, diff_path,
                                    threshold=config.get("diff_threshold", 10),
                                )
                                icon = "✅" if similarity >= 95 else "⚠️ "
                                print(f"   {icon} Visual match: {similarity:.1f}%")
                        except Exception as e:
                            print(f"   ⚠️  Figma comparison failed: {e}")
                    else:
                        print(f"   ℹ️  No Figma frame mapped for '{path}'")

                vp_results.append({
                    "viewport": vp, "live_path": live_path,
                    "figma_path": figma_path, "diff_path": diff_path,
                    "similarity": similarity,
                })

            results.append({"url": page_url, "path": path, "seo": seo, "viewports": vp_results})

    print(f"\n{'═'*55}")
    print("📊 Generating HTML report...")
    report_path = generate_report(results, config, output_dir, timestamp, site_seo=site_seo)
    print(f"✅ Done! Report ready.")
    return report_path


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _cleanup_old_jobs():
    """Removes jobs and reports older than JOB_TTL_SECONDS."""
    while True:
        time.sleep(3600)  # run hourly
        cutoff = time.time() - JOB_TTL_SECONDS
        with _jobs_lock:
            stale = [jid for jid, j in _jobs.items() if j.created_at < cutoff]
        for jid in stale:
            report_dir = os.path.join(REPORTS_DIR, jid)
            if os.path.exists(report_dir):
                shutil.rmtree(report_dir, ignore_errors=True)
            with _jobs_lock:
                _jobs.pop(jid, None)


threading.Thread(target=_cleanup_old_jobs, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run():
    """Start a new QA job. Returns {job_id}."""
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"Max concurrent jobs ({MAX_CONCURRENT_JOBS}) reached. Please wait."}), 429

    data = request.json or {}

    # Validate
    site_url = (data.get("site_url") or "").strip()
    if not site_url or not site_url.startswith("http"):
        return jsonify({"error": "Invalid site_url"}), 400

    # Build config
    figma_token    = (data.get("figma_token") or "").strip()
    figma_file_id  = (data.get("figma_file_id") or "").strip()
    raw_frames     = data.get("page_frames") or []  # [{path, frames: {Desktop: id, Tablet: id, Mobile: id}}]
    page_frames    = {}
    for r in raw_frames:
        p = (r.get("path") or "").strip().rstrip("/") or "/"
        vp_frames = r.get("frames") or {}
        if vp_frames:
            page_frames[p] = {k: v for k, v in vp_frames.items() if v}

    raw_viewports  = data.get("viewports") or []
    viewports = []
    for vp in raw_viewports:
        try:
            viewports.append({"name": str(vp["name"]), "width": int(vp["width"]), "height": int(vp["height"])})
        except Exception:
            pass
    if not viewports:
        viewports = [
            {"name": "Desktop", "width": 1440, "height": 900},
            {"name": "Tablet",  "width": 768,  "height": 1024},
            {"name": "Mobile",  "width": 375,  "height": 812},
        ]

    config = {
        "site_url": site_url,
        "figma": {
            "api_token":   figma_token,
            "file_id":     figma_file_id,
            "page_frames": page_frames,
        },
        "viewports":      viewports,
        "diff_threshold": int(data.get("diff_threshold", 10)),
        "timeout_ms":     int(data.get("timeout_ms", 15000)),
        "output_dir":     REPORTS_DIR,
    }

    job_id = uuid.uuid4().hex[:10]
    job    = Job(job_id, config)
    with _jobs_lock:
        _jobs[job_id] = job

    thread = threading.Thread(target=_thread_run_job, args=(job_id,), daemon=True)
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id: str):
    """Poll job status + incremental logs."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        abort(404)
    since = int(request.args.get("since", 0))
    return jsonify(job.to_dict(include_logs_from=since))


@app.route("/api/figma/frames", methods=["POST"])
def api_figma_frames():
    """Lists all frames in a Figma file. Used by the UI for mapping setup."""
    data = request.json or {}
    token   = (data.get("api_token") or "").strip()
    file_id = (data.get("file_id") or "").strip()

    if not token or not file_id:
        return jsonify({"error": "api_token and file_id are required"}), 400

    try:
        from modules.figma import FigmaClient
        client = FigmaClient(token, file_id)
        frames = client.list_frames()
        return jsonify({"frames": frames})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/reports/<job_id>/report.html")
def serve_report(job_id: str):
    """Serves the generated HTML report."""
    report_dir = os.path.join(REPORTS_DIR, job_id)
    if not os.path.exists(os.path.join(report_dir, "report.html")):
        abort(404)
    return send_from_directory(report_dir, "report.html")


@app.route("/reports/<job_id>/screenshots/<filename>")
def serve_screenshot(job_id: str, filename: str):
    """Serves individual screenshot files referenced by the report."""
    shots_dir = os.path.join(REPORTS_DIR, job_id, "screenshots")
    return send_from_directory(shots_dir, filename)


@app.route("/api/jobs")
def api_jobs():
    """Returns a list of recent jobs (most recent first)."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jsonify([{
        "id":         j.id,
        "status":     j.status,
        "site_url":   j.config["site_url"],
        "created_at": j.created_at,
        "report_url": j.report_url,
    } for j in jobs[:20]])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    print(f"🚀  Framer QA Server → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
