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
import shutil
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
        self.favicon_url: str | None = None
        self.total_pass: int | None = None
        self.total_warn: int | None = None
        self.total_fail: int | None = None
        self.error: str | None = None
        self.created_at = time.time()
        self._lock = threading.Lock()

    def append_log(self, msg: str):
        with self._lock:
            self.logs.append(msg)
            self._update_progress(msg)

    def _update_progress(self, msg: str):
        """Heuristically updates progress from log messages."""
        if "Discovering pages" in msg:
            self.progress = 0.05
        elif "Running SEO checks" in msg:
            self.progress = min(self.progress + 0.08, 0.85)
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
                "total_pass":  self.total_pass,
                "total_warn":  self.total_warn,
                "total_fail":  self.total_fail,
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
    """Core async QA runner — SEO checks only."""
    from modules.crawler     import get_pages_from_sitemap
    from modules.screenshots import ScreenshotTaker
    from modules.reporter    import generate_report

    config   = job.config
    site_url = config["site_url"].rstrip("/")

    # Output dir
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_dir = os.path.join(REPORTS_DIR, job.id)
    os.makedirs(output_dir, exist_ok=True)

    print(f"{'═'*55}")
    print(f"  Framer QA — {site_url}")
    print(f"{'═'*55}")

    # Discover pages
    print("\n🔗  Discovering pages from sitemap...")
    pages = get_pages_from_sitemap(site_url)
    print(f"   Found {len(pages)} page(s)")

    def page_path(url):
        p = url.replace(site_url, "").strip().rstrip("/")
        return p or "/"

    results = []
    total = len(pages)

    async with ScreenshotTaker(timeout_ms=config.get("timeout_ms", 15000)) as taker:

        # Site-level SEO — homepage check
        site_seo = None
        print("\n🌐 Checking site-level SEO (language, favicon, social preview)...")
        try:
            site_seo = await taker.check_site_seo(site_url)
            p, w, f = site_seo["pass_count"], site_seo["warn_count"], site_seo["fail_count"]
            print(f"   ✅ {p} pass  ⚠️  {w} warn  ❌ {f} fail")
        except Exception as e:
            print(f"   ⚠️  Site SEO check failed: {e}")

        for idx, page_url in enumerate(pages):
            path = page_path(page_url)
            print(f"\n{'─'*55}")
            print(f"📄 [{idx+1}/{total}] {path}")
            job.progress = 0.05 + (idx / total) * 0.88

            print("   🔎 Running SEO checks...")
            try:
                seo = await taker.check_seo(page_url)
                print(f"   ✅ {seo['pass_count']} pass  ⚠️  {seo['warn_count']} warn  ❌ {seo['fail_count']} fail")
            except Exception as e:
                print(f"   ⚠️  SEO check failed: {e}")
                seo = {"url": page_url, "raw": {}, "checks": [], "pass_count": 0, "warn_count": 0, "fail_count": 1}

            results.append({"url": page_url, "path": path, "seo": seo})

    # Flag duplicate meta titles/descriptions across pages
    _flag_duplicate_meta(results)

    print(f"\n{'═'*55}")
    print("📊 Generating HTML report...")
    report_path = generate_report(results, config, output_dir, timestamp, site_seo=site_seo)
    print(f"✅ Done! Report ready.")

    if site_seo:
        job.favicon_url = site_seo.get("raw", {}).get("favicon_href")

    total_pass = sum(r["seo"]["pass_count"] for r in results)
    total_warn = sum(r["seo"]["warn_count"] for r in results)
    total_fail = sum(r["seo"]["fail_count"] for r in results)
    job.total_pass = total_pass
    job.total_warn = total_warn
    job.total_fail = total_fail

    _save_job_meta(job, f"/reports/{job.id}/report.html")

    return report_path


# ── Duplicate meta detection ─────────────────────────────────────────────────

def _flag_duplicate_meta(results: list):
    """Flags pages sharing identical meta titles or descriptions."""
    title_map: dict[str, list[str]] = {}
    desc_map:  dict[str, list[str]] = {}

    for r in results:
        seo_raw = (r.get("seo") or {}).get("raw") or {}
        path    = r.get("path", "?")
        title   = seo_raw.get("title")
        desc    = seo_raw.get("meta_description")
        if title:
            title_map.setdefault(title, []).append(path)
        if desc:
            desc_map.setdefault(desc, []).append(path)

    for r in results:
        seo     = r.get("seo") or {}
        seo_raw = seo.get("raw") or {}
        path    = r.get("path", "?")
        title   = seo_raw.get("title")
        desc    = seo_raw.get("meta_description")

        if title and len(title_map.get(title, [])) > 1:
            dupes = [p for p in title_map[title] if p != path]
            seo.setdefault("checks", []).append({
                "name":   "Duplicate Meta Title",
                "status": "warn",
                "detail": f"Same title also used on: {', '.join(dupes[:3])}{'…' if len(dupes) > 3 else ''}",
                "value":  title,
            })
            seo["warn_count"] = seo.get("warn_count", 0) + 1

        if desc and len(desc_map.get(desc, [])) > 1:
            dupes = [p for p in desc_map[desc] if p != path]
            seo.setdefault("checks", []).append({
                "name":   "Duplicate Meta Description",
                "status": "warn",
                "detail": f"Same description also used on: {', '.join(dupes[:3])}{'…' if len(dupes) > 3 else ''}",
                "value":  desc,
            })
            seo["warn_count"] = seo.get("warn_count", 0) + 1


# ── History persistence ───────────────────────────────────────────────────────

def _save_job_meta(job: "Job", report_url: str):
    try:
        meta = {
            "id":          job.id,
            "site_url":    job.config["site_url"],
            "status":      job.status,
            "created_at":  job.created_at,
            "report_url":  report_url,
            "favicon_url": job.favicon_url,
            "total_pass":  job.total_pass,
            "total_warn":  job.total_warn,
            "total_fail":  job.total_fail,
            "config":      job.config,
        }
        job_dir = os.path.join(REPORTS_DIR, job.id)
        os.makedirs(job_dir, exist_ok=True)
        with open(os.path.join(job_dir, "meta.json"), "w") as f:
            json.dump(meta, f)
    except Exception as e:
        _orig_print(f"[History] Could not save meta for {job.id}: {e}")


def _load_disk_jobs() -> list[dict]:
    disk_jobs = []
    try:
        for job_id in os.listdir(REPORTS_DIR):
            meta_path = os.path.join(REPORTS_DIR, job_id, "meta.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path) as f:
                        disk_jobs.append(json.load(f))
                except Exception:
                    pass
    except Exception:
        pass
    return disk_jobs


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _cleanup_old_jobs():
    while True:
        time.sleep(3600)
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

    site_url = (data.get("site_url") or "").strip()
    if not site_url or not site_url.startswith("http"):
        return jsonify({"error": "Invalid site_url"}), 400

    config = {
        "site_url":   site_url,
        "timeout_ms": int(data.get("timeout_ms", 15000)),
        "output_dir": REPORTS_DIR,
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
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        abort(404)
    since = int(request.args.get("since", 0))
    return jsonify(job.to_dict(include_logs_from=since))


@app.route("/reports/<job_id>/report.html")
def serve_report(job_id: str):
    report_dir = os.path.join(REPORTS_DIR, job_id)
    if not os.path.exists(os.path.join(report_dir, "report.html")):
        abort(404)
    return send_from_directory(report_dir, "report.html")


@app.route("/api/jobs")
def api_jobs():
    with _jobs_lock:
        mem_jobs = list(_jobs.values())
    mem_ids = {j.id for j in mem_jobs}

    disk_jobs = [d for d in _load_disk_jobs() if d["id"] not in mem_ids]

    combined = [{
        "id":          j.id,
        "status":      j.status,
        "site_url":    j.config["site_url"],
        "created_at":  j.created_at,
        "report_url":  j.report_url,
        "favicon_url": j.favicon_url,
    } for j in mem_jobs] + disk_jobs

    combined.sort(key=lambda j: j["created_at"], reverse=True)
    return jsonify(combined[:50])


@app.route("/api/pages")
def api_pages():
    url = (request.args.get("url") or "").strip()
    if not url or not url.startswith("http"):
        return jsonify({"error": "Invalid URL"}), 400
    try:
        from modules.crawler import get_pages_from_sitemap
        site_url = url.rstrip("/")
        pages    = get_pages_from_sitemap(site_url)
        paths    = []
        for p in pages:
            path = p.replace(site_url, "").strip().rstrip("/") or "/"
            if path not in paths:
                paths.append(path)
        return jsonify({"paths": paths})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rerun/<job_id>", methods=["POST"])
def api_rerun(job_id: str):
    if _running_job_count() >= MAX_CONCURRENT_JOBS:
        return jsonify({"error": f"Max concurrent jobs ({MAX_CONCURRENT_JOBS}) reached."}), 429

    meta_path = os.path.join(REPORTS_DIR, job_id, "meta.json")
    if not os.path.exists(meta_path):
        return jsonify({"error": "Job not found"}), 404

    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        return jsonify({"error": "Could not read job metadata"}), 500

    config = meta.get("config")
    if not config:
        return jsonify({"error": "No config saved for this job — cannot re-run"}), 400

    new_job_id = uuid.uuid4().hex[:10]
    new_job    = Job(new_job_id, config)
    with _jobs_lock:
        _jobs[new_job_id] = new_job

    thread = threading.Thread(target=_thread_run_job, args=(new_job_id,), daemon=True)
    thread.start()
    return jsonify({"job_id": new_job_id})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    print(f"🚀  Framer QA Server → http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)
