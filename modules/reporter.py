"""
reporter.py — Generates a self-contained HTML QA report.

The report includes:
  • Summary dashboard (pass rate, issue count)
  • Site-level SEO checks (language, favicon, social preview)
  • Per-page SEO/meta checklist table
"""

import os
from datetime import datetime, timezone


def generate_report(results: list[dict], config: dict, output_dir: str, timestamp: str,
                    site_seo: dict | None = None) -> str:
    """Generates the HTML report and returns its file path."""
    report_path = os.path.join(output_dir, "report.html")

    site_url    = config["site_url"]
    now         = datetime.now(timezone.utc)
    utc_iso     = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    date_str    = "<span class=\"report-date\" data-utc=\"" + utc_iso + "\"></span>"
    total_pages = len(results)

    total_pass = sum(r["seo"]["pass_count"] for r in results)
    total_warn = sum(r["seo"]["warn_count"] for r in results)
    total_fail = sum(r["seo"]["fail_count"] for r in results)

    html = _render_html(
        site_url=site_url,
        date_str=date_str,
        total_pages=total_pages,
        total_pass=total_pass,
        total_warn=total_warn,
        total_fail=total_fail,
        results=results,
        site_seo=site_seo,
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path


# ══════════════════════════════════════════════════════════════════════════════
# HTML rendering
# ══════════════════════════════════════════════════════════════════════════════

def _render_html(*, site_url, date_str, total_pages, total_pass, total_warn,
                 total_fail, results, site_seo=None):

    site_url_safe = site_url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_").replace("-", "_")

    # Score & summary sentence
    total_checks = total_pass + total_warn + total_fail
    score = round((total_pass + total_warn * 0.5) / total_checks * 100) if total_checks else 100
    if total_fail == 0 and total_warn == 0:
        summary_sentence = "Everything looks great — all checks passed."
        summary_color = "var(--pass)"
    elif total_fail == 0:
        summary_sentence = f"Looking good — {total_warn} warning{'s' if total_warn != 1 else ''} to review."
        summary_color = "var(--warn)"
    elif total_fail <= 3:
        summary_sentence = f"Needs attention — {total_fail} issue{'s' if total_fail != 1 else ''} and {total_warn} warning{'s' if total_warn != 1 else ''} found."
        summary_color = "var(--fail)"
    else:
        summary_sentence = f"Issues detected — {total_fail} critical issues need fixing."
        summary_color = "var(--fail)"

    seo_table_rows = "\n".join(_render_seo_row(r) for r in results)
    seo_check_names = []
    for r in results:
        names = [c["name"] for c in (r.get("seo") or {}).get("checks") or []]
        if names:
            seo_check_names = names
            break
    seo_headers = "\n".join(f"<th>{name}</th>" for name in seo_check_names)

    site_seo_html = _render_site_seo_section(site_seo) if site_seo else ""

    # Sidebar navigation links for each page
    def _sidebar_page_link(r):
        path      = r.get("path", "/") or "/"
        sid       = path.strip("/").replace("/", "_") or "home"
        label     = path if path != "/" else "/"
        seo       = r.get("seo", {})
        dot_color = "#f04438" if seo.get("fail_count") else ("#f79009" if seo.get("warn_count") else "#12b76a")
        return (f'<a href="#page-{sid}" class="nav-item">'
                f'<span class="nav-dot" style="background:{dot_color}"></span>'
                f'{label}</a>')
    sidebar_links = "\n".join(_sidebar_page_link(r) for r in results)

    pages_html = "\n".join(_render_page(r) for r in results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Framer QA Report — {site_url}</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg width='250' height='250' viewBox='0 0 250 250' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='250' height='250' rx='48' fill='%23070707'/%3E%3Cpath d='M175.24 94.6419C175.24 63.3188 154.171 54 113.301 54H69V195H93.3096V135.636H116.898C119.418 135.636 121.846 135.636 124.192 135.452L153.541 194.992H181L149.131 130.977C166.595 124.949 175.24 112.709 175.24 94.6335V94.6419ZM117.528 116.008H93.4008V73.813H116.724C135.903 73.813 150.308 76.3736 150.308 94.8182C150.308 111.71 138.423 116.008 117.536 116.008H117.528Z' fill='%23FAFAFA'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --surface:      #ffffff;
    --shell-bg:     #f9fafb;
    --border:       #e4e7ec;
    --border2:      #f2f4f7;
    --text:         #101828;
    --muted:        #667085;
    --muted2:       #98a2b3;
    --subtle:       #f9fafb;
    --pass:         #12b76a;
    --warn:         #f79009;
    --fail:         #f04438;
    --accent:       #101828;
    --accent-h:     #1d2939;
    --accent-light: #f2f4f7;
    --pass-light:   #ecfdf3;
    --pass-text:    #027a48;
    --warn-light:   #fffaeb;
    --warn-text:    #b54708;
    --fail-light:   #fef3f2;
    --fail-text:    #b42318;
    --shadow-sm:    0 2px 8px rgba(16,24,40,.03), 0 1px 3px rgba(16,24,40,.02);
    --shadow:       0 8px 28px rgba(16,24,40,.04), 0 2px 8px rgba(16,24,40,.03);
    --radius:       12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--shell-bg);
    min-height: 100vh;
    color: var(--text);
    font-size: 14px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* ── App Shell ── */
  .app-shell {{
    display: flex;
    height: 100vh;
    background: var(--shell-bg);
    overflow: hidden;
  }}

  /* ── Sidebar ── */
  .sidebar {{
    width: 216px;
    flex-shrink: 0;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }}
  .sidebar-brand {{
    padding: 18px 16px 14px;
    border-bottom: 1px solid var(--border2);
    display: flex;
    align-items: center;
    gap: 10px;
  }}
  .sidebar-logo {{
    width: 32px; height: 32px;
    border-radius: 9px;
    overflow: hidden;
    flex-shrink: 0;
    cursor: pointer;
    transition: opacity .15s;
  }}
  .sidebar-logo:hover {{ opacity: 0.8; }}
  .sidebar-brand-name {{
    font-size: 13px; font-weight: 700;
    color: var(--text); letter-spacing: -0.2px;
  }}
  .sidebar-meta {{
    padding: 12px 16px;
    border-bottom: 1px solid var(--border2);
  }}
  .sidebar-site {{
    display: inline-flex; align-items: center;
    font-size: 11px; font-weight: 500;
    color: var(--accent);
    background: var(--accent-light);
    border: 1px solid rgba(16,24,40,.08);
    border-radius: 20px;
    padding: 3px 10px;
    max-width: 100%;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    margin-bottom: 6px;
    text-decoration: none;
  }}
  .sidebar-site:hover {{ opacity: 0.8; text-decoration: none; }}
  .sidebar-date {{
    font-size: 10.5px;
    color: var(--muted2);
  }}
  .sidebar-nav {{
    flex: 1;
    overflow-y: auto;
    padding: 10px 8px;
  }}
  .nav-section-label {{
    font-size: 10px; font-weight: 600;
    text-transform: uppercase; letter-spacing: .8px;
    color: var(--muted2);
    padding: 10px 8px 4px;
  }}
  .nav-item {{
    display: flex; align-items: center; gap: 8px;
    padding: 6px 10px;
    border-radius: 8px;
    color: var(--muted);
    font-size: 12.5px; font-weight: 500;
    text-decoration: none;
    transition: background .12s, color .12s;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: pointer;
  }}
  .nav-item:hover {{ background: var(--subtle); color: var(--text); text-decoration: none; }}
  .nav-item.active {{ background: var(--accent-light); color: var(--accent); font-weight: 600; }}
  .nav-item-icon {{ font-size: 13px; flex-shrink: 0; }}
  .nav-dot {{
    width: 7px; height: 7px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .sidebar-actions {{
    padding: 10px 8px;
    border-top: 1px solid var(--border2);
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  .sidebar-btn {{
    display: flex; align-items: center; gap: 8px;
    padding: 7px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    font-size: 12px; font-weight: 500;
    cursor: pointer;
    transition: all .15s;
    font-family: inherit;
    width: 100%;
  }}
  .sidebar-btn:hover {{ border-color: var(--accent); color: var(--accent); background: var(--accent-light); }}

  /* ── Main Content ── */
  .main-content {{
    flex: 1;
    overflow-y: auto;
    background: var(--shell-bg);
  }}
  .main-inner {{
    padding: 36px 44px;
    max-width: 1100px;
  }}

  /* ── Page heading ── */
  .page-heading {{
    margin-bottom: 28px;
  }}
  .page-heading h2 {{
    font-size: 22px; font-weight: 800;
    color: var(--text); letter-spacing: -0.4px;
    margin-bottom: 4px;
  }}
  .page-heading .sub {{
    font-size: 13px; color: var(--muted);
  }}
  .page-heading .sub a {{ color: var(--accent); }}
  .summary-sentence {{ font-size: 14px; font-weight: 500; margin-top: 8px; letter-spacing: -0.1px; }}

  /* ── Summary Cards ── */
  .summary {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 12px;
    margin-bottom: 36px;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 22px;
    box-shadow: var(--shadow-sm);
  }}
  .stat-value {{
    font-size: 30px; font-weight: 600;
    line-height: 1; margin-bottom: 6px;
    letter-spacing: -1px;
  }}
  .stat-label {{
    color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: .7px; font-weight: 600;
  }}
  .pass    {{ color: var(--pass); }}
  .warn    {{ color: var(--warn); }}
  .fail    {{ color: var(--fail); }}
  .neutral {{ color: var(--accent); }}

  /* ── Section ── */
  .section {{ margin-bottom: 36px; }}
  .section-title {{
    font-size: 11px; font-weight: 700; letter-spacing: -0.1px;
    margin-bottom: 14px;
    color: var(--muted2);
    display: flex; align-items: center; gap: 8px;
    letter-spacing: .8px; text-transform: uppercase;
  }}
  .section-title .section-icon {{
    width: 20px; height: 20px; border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; background: var(--border2); flex-shrink: 0;
  }}
  .section-subtitle {{
    color: var(--muted); font-size: 12px;
    margin-top: -8px; margin-bottom: 14px; padding-left: 28px;
  }}

  /* ── SEO Table ── */
  .table-wrap {{
    overflow-x: auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    box-shadow: var(--shadow-sm);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th, td {{
    padding: 10px 16px;
    border-bottom: 1px solid var(--border2);
    white-space: nowrap;
  }}
  tbody tr:last-child td {{ border-bottom: none; }}
  th {{
    background: var(--subtle);
    color: var(--muted);
    font-weight: 600;
    font-size: 10.5px;
    text-transform: uppercase;
    letter-spacing: .6px;
    text-align: left;
    position: sticky;
    top: 0;
    z-index: 2;
    border-bottom: 1px solid var(--border);
  }}
  tbody tr:hover td {{ background: var(--subtle); }}
  .page-url {{ color: var(--accent); font-weight: 500; font-size: 12.5px; }}

  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    position: relative;
    letter-spacing: .1px;
  }}
  .badge.pass {{ background: var(--pass-light); color: var(--pass-text); }}
  .badge.warn {{ background: var(--warn-light); color: var(--warn-text); }}
  .badge.fail {{ background: var(--fail-light); color: var(--fail-text); }}

  /* ── Instant custom tooltip ── */
  .badge[data-tip]::after {{
    content: attr(data-tip);
    position: absolute;
    bottom: calc(100% + 6px);
    left: 50%;
    transform: translateX(-50%);
    background: #1e1e2e;
    color: #cdd6f4;
    font-size: 11px;
    font-weight: 400;
    line-height: 1.5;
    width: max-content;
    max-width: 280px;
    white-space: normal;
    word-break: break-word;
    padding: 5px 9px;
    border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,.07);
    pointer-events: none;
    opacity: 0;
    transition: opacity .1s;
    z-index: 100;
  }}
  .badge[data-tip]:hover::after {{
    opacity: 1;
  }}

  /* ── Page Cards ── */
  .page-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 10px;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    transition: box-shadow .2s, border-color .2s;
  }}
  .page-card:hover {{ box-shadow: var(--shadow); border-color: #c4c9d4; }}
  .page-card-header {{
    padding: 13px 18px;
    border-bottom: 1px solid transparent;
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
    transition: background .1s;
  }}
  .page-card-header:hover {{ background: var(--subtle); }}
  .page-card.open .page-card-header {{ border-bottom-color: var(--border2); }}
  .page-card-header h3 {{ font-size: 13.5px; font-weight: 600; color: var(--text); letter-spacing: -0.1px; }}
  .page-card-header .url {{ color: var(--muted2); font-size: 11px; margin-top: 1px; }}
  .chevron {{ color: var(--muted2); transition: transform .2s; }}
  .chevron {{ transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
  .page-card.open .chevron {{ transform: rotate(180deg); }}
  .page-card-body {{
    height: 0;
    overflow: hidden;
    transition: height 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }}
  .page-card-body-inner {{ padding: 18px; }}

  /* ── Site-level checks grid ── */
  .site-checks-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
  }}
  .site-check-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    box-shadow: var(--shadow-sm);
    transition: box-shadow .2s, border-color .2s;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
    overflow-wrap: break-word;
    word-break: break-word;
  }}
  .site-check-card:hover {{ box-shadow: var(--shadow); border-color: #c4c9d4; }}
  .site-check-card.wide-card {{
    grid-column: span 2;
  }}
  @media (max-width: 900px) {{
    .site-checks-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .site-check-card.wide-card {{ grid-column: span 2; }}
  }}
  @media (max-width: 560px) {{
    .site-checks-grid {{ grid-template-columns: 1fr; }}
    .site-check-card.wide-card {{ grid-column: span 1; }}
  }}
  .site-check-header {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .site-check-dot {{
    width: 8px; height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .site-check-card.pass .site-check-dot {{ background: var(--pass); }}
  .site-check-card.warn .site-check-dot {{ background: var(--warn); }}
  .site-check-card.fail .site-check-dot {{ background: var(--fail); }}
  .site-check-name {{ font-weight: 700; font-size: 13px; color: var(--text); }}
  .site-check-detail {{
    color: var(--muted);
    font-size: 12.5px;
    line-height: 1.55;
    padding-left: 16px;
  }}
  .site-check-value {{
    margin-top: 4px;
    font-size: 11.5px;
    color: var(--muted);
    word-break: break-all;
    line-height: 1.5;
    padding-left: 16px;
  }}
  .favicon-preview {{
    display: flex;
    gap: 8px;
    margin-top: 10px;
    padding-left: 16px;
  }}
  .favicon-bg {{
    width: 52px; height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    border: 1px solid var(--border);
    flex-shrink: 0;
  }}
  .favicon-bg-white {{ background: #ffffff; box-shadow: inset 0 0 0 1px #e5e7eb; }}
  .favicon-bg-black {{ background: #111111; }}
  .favicon-bg img {{ width: 32px; height: 32px; object-fit: contain; }}
  .og-image-preview {{
    margin-top: 10px;
    border-radius: 8px;
    overflow: hidden;
    border: 1px solid var(--border);
    max-width: 600px;
  }}
  .og-image-preview img {{
    width: 100%;
    display: block;
    max-height: 315px;
    object-fit: cover;
  }}
  .char-over {{
    color: #f04438;
    background: #fee2e2;
    border-radius: 2px;
    padding: 0 1px;
  }}

  /* ── Per-page check list ── */
  .check-list {{
    display: flex;
    flex-direction: column;
    gap: 0;
  }}
  .check-row {{
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 9px 0;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    line-height: 1.4;
  }}
  .check-row:last-child {{ border-bottom: none; }}
  .check-icon {{ flex-shrink: 0; font-size: 13px; width: 18px; }}
  .check-name {{
    font-weight: 500;
    color: var(--text);
    min-width: 140px;
    flex-shrink: 0;
  }}
  .check-detail {{ color: var(--muted); flex: 1; }}
  .check-value {{
    font-size: 12px;
    color: var(--muted);
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .check-action-pill {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 9px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    color: #6941c6;
    background: #f4f3ff;
    border: 1px solid #d9d6fe;
    text-decoration: none;
    white-space: nowrap;
    flex-shrink: 0;
    transition: background .15s, border-color .15s;
    letter-spacing: 0;
  }}
  .check-action-pill:hover {{
    background: #ede9fe;
    border-color: #c4b5fd;
    text-decoration: none;
  }}
  .check-action-pill svg {{ flex-shrink: 0; }}

  /* ── Footer ── */
  .footer {{
    border-top: 1px solid var(--border2);
    padding: 16px 44px;
    color: var(--muted2);
    font-size: 11px;
    text-align: center;
    letter-spacing: .1px;
  }}

  /* ── Print ── */
  @media print {{
    body {{ background: white !important; }}
    .app-shell {{ height: auto; display: block; }}
    .sidebar {{ display: none !important; }}
    .main-content {{ overflow: visible; }}
    .main-inner {{ padding: 24px; max-width: 100%; }}
    .sidebar-btn {{ display: none !important; }}
    .page-card-body {{ height: auto !important; }}
    .page-card {{ break-inside: avoid; margin-bottom: 24px; box-shadow: none; }}
    .stat-card {{ break-inside: avoid; print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .summary {{ grid-template-columns: repeat(4, 1fr); }}
    .site-checks-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}
</style>
</head>
<body>

<div class="app-shell">

  <!-- ── Sidebar ── -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-logo" onclick="window.location.href='/'" title="Back to Framer QA"><svg width="32" height="32" viewBox="0 0 250 250" fill="none" xmlns="http://www.w3.org/2000/svg"><rect width="250" height="250" fill="#070707"/><path d="M175.24 94.6419C175.24 63.3188 154.171 54 113.301 54H69V195H93.3096V135.636H116.898C119.418 135.636 121.846 135.636 124.192 135.452L153.541 194.992H181L149.131 130.977C166.595 124.949 175.24 112.709 175.24 94.6335V94.6419ZM117.528 116.008H93.4008V73.813H116.724C135.903 73.813 150.308 76.3736 150.308 94.8182C150.308 111.71 138.423 116.008 117.536 116.008H117.528Z" fill="#FAFAFA"/></svg></div>
      <span class="sidebar-brand-name">Framer QA</span>
    </div>
    <div class="sidebar-meta">
      <a href="{site_url}" target="_blank" class="sidebar-site">{site_url}</a>
      <div class="sidebar-date">{date_str}</div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section-label">Report</div>
      <a href="#summary" class="nav-item"><span class="nav-item-icon">📊</span> Overview</a>
      <a href="#site-checks" class="nav-item"><span class="nav-item-icon">🌐</span> Site Checks</a>
      <a href="#seo-table" class="nav-item"><span class="nav-item-icon">📋</span> Page SEO</a>
      <div class="nav-section-label">Per-page breakdown</div>
      {sidebar_links}
    </nav>
    <div class="sidebar-actions">
      <button class="sidebar-btn" id="copy-link-btn" onclick="copyReportLink(this)">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
        Copy Link
      </button>
      <button class="sidebar-btn" onclick="savePDF()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        Save PDF
      </button>
    </div>
  </aside>

  <!-- ── Main Content ── -->
  <main class="main-content">
    <div class="main-inner">

      <div class="page-heading" id="summary">
        <h2>QA Report</h2>
        <div class="sub">{total_pages} page{"s" if total_pages != 1 else ""} checked &nbsp;·&nbsp; {date_str}</div>
        <div class="summary-sentence" style="color:{summary_color}">{summary_sentence}</div>
      </div>

      <div class="summary">
        <div class="stat-card">
          <div class="stat-value neutral">{score}</div>
          <div class="stat-label">Score</div>
        </div>
        <div class="stat-card">
          <div class="stat-value neutral">{total_pages}</div>
          <div class="stat-label">Pages Checked</div>
        </div>
        <div class="stat-card">
          <div class="stat-value pass">{total_pass}</div>
          <div class="stat-label">SEO Passed</div>
        </div>
        <div class="stat-card">
          <div class="stat-value warn">{total_warn}</div>
          <div class="stat-label">Warnings</div>
        </div>
        <div class="stat-card">
          <div class="stat-value fail">{total_fail}</div>
          <div class="stat-label">Failures</div>
        </div>
      </div>

      <div id="site-checks">
        {site_seo_html}
      </div>

      <div class="section" id="seo-table">
        <div class="section-title"><span class="section-icon">📋</span> Page-level SEO</div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Page</th>
                {seo_headers}
              </tr>
            </thead>
            <tbody>
              {seo_table_rows}
            </tbody>
          </table>
        </div>
      </div>

      <div class="section" id="pages">
        <div class="section-title"><span class="section-icon">📄</span> SEO breakdown per page</div>
        {pages_html}
      </div>

      <div class="footer">Framer QA &nbsp;·&nbsp; {date_str}</div>

    </div>
  </main>

</div>

<script>
  function copyReportLink(btn) {{
    const url = window.location.href;
    navigator.clipboard.writeText(url).then(() => {{
      const orig = btn.innerHTML;
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
      btn.style.color = '#12b76a';
      setTimeout(() => {{ btn.innerHTML = orig; btn.style.color = ''; }}, 2000);
    }}).catch(() => {{
      const ta = document.createElement('textarea');
      ta.value = url;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      btn.textContent = 'Copied!';
      setTimeout(() => {{ btn.textContent = 'Copy Link'; }}, 2000);
    }});
  }}

  function savePDF() {{
    document.querySelectorAll('.page-card').forEach(c => c.classList.add('open'));
    window.print();
  }}

  if (new URLSearchParams(window.location.search).get('autoprint') === '1') {{
    document.querySelectorAll('.page-card').forEach(c => c.classList.add('open'));
    window.addEventListener('load', () => setTimeout(() => window.print(), 800));
  }}

  // Sidebar scroll-spy
  const mainEl = document.querySelector('.main-content');
  const navLinks = document.querySelectorAll('.sidebar-nav .nav-item[href^="#"]');
  function updateActivNav() {{
    let current = null;
    navLinks.forEach(a => {{
      const target = document.querySelector(a.getAttribute('href'));
      if (target) {{
        const rect = target.getBoundingClientRect();
        const containerTop = mainEl.getBoundingClientRect().top;
        if (rect.top - containerTop <= 80) current = a;
      }}
    }});
    navLinks.forEach(a => a.classList.remove('active'));
    if (current) current.classList.add('active');
  }}
  mainEl && mainEl.addEventListener('scroll', updateActivNav);
  updateActivNav();

  // Smooth scroll for Report nav links
  document.querySelectorAll('.sidebar-nav .nav-item[href^="#"]:not([href^="#page-"])').forEach(a => {{
    a.addEventListener('click', e => {{
      e.preventDefault();
      const target = document.querySelector(a.getAttribute('href'));
      if (target && mainEl) {{
        const targetTop = target.getBoundingClientRect().top - mainEl.getBoundingClientRect().top + mainEl.scrollTop - 48;
        mainEl.scrollTo({{ top: targetTop, behavior: 'smooth' }});
      }}
    }});
  }});

  // Smooth accordion helpers
  function openCard(card) {{
    const body = card.querySelector('.page-card-body');
    card.classList.add('open');
    body.style.height = body.scrollHeight + 'px';
    body.addEventListener('transitionend', () => {{
      if (card.classList.contains('open')) body.style.height = 'auto';
    }}, {{ once: true }});
  }}
  function closeCard(card) {{
    const body = card.querySelector('.page-card-body');
    body.style.height = body.scrollHeight + 'px';
    requestAnimationFrame(() => {{
      body.style.height = '0';
    }});
    card.classList.remove('open');
  }}

  // Page card accordion
  document.querySelectorAll('.page-card-header').forEach(header => {{
    header.addEventListener('click', () => {{
      const card = header.closest('.page-card');
      card.classList.contains('open') ? closeCard(card) : openCard(card);
    }});
  }});

  // Sidebar page links — expand instantly, then smooth-scroll to fully open card
  document.querySelectorAll('.sidebar-nav .nav-item[href^="#page-"]').forEach(a => {{
    a.addEventListener('click', e => {{
      e.preventDefault();
      const card = document.querySelector(a.getAttribute('href'));
      if (!card) return;
      // Expand instantly (no transition) so we scroll to the full card height
      const body = card.querySelector('.page-card-body');
      body.style.transition = 'none';
      card.classList.add('open');
      body.style.height = 'auto';
      body.offsetHeight; // force reflow
      body.style.transition = ''; // restore transition for future toggles
      // Now scroll with full card height known
      const cardTop = card.getBoundingClientRect().top - mainEl.getBoundingClientRect().top + mainEl.scrollTop - 48;
      mainEl.scrollTo({{ top: cardTop, behavior: 'smooth' }});
    }});
  }});

  // Open first card by default
  const firstCard = document.querySelector('.page-card');
  if (firstCard) openCard(firstCard);

  // Render timestamps in the user's local timezone
  document.querySelectorAll('.report-date').forEach(el => {{
    const utc = el.dataset.utc;
    if (!utc) return;
    const d = new Date(utc);
    const offset = -d.getTimezoneOffset();
    const sign   = offset >= 0 ? '+' : '-';
    const hrs    = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0');
    const mins   = String(Math.abs(offset) % 60).padStart(2, '0');
    const tz     = mins === '00' ? `GMT${{sign}}${{parseInt(hrs)}}` : `GMT${{sign}}${{hrs}}:${{mins}}`;
    const formatted = d.toLocaleDateString('en-US', {{ month: 'long', day: '2-digit', year: 'numeric' }})
                    + ' at '
                    + d.toLocaleTimeString('en-US', {{ hour: '2-digit', minute: '2-digit', hour12: false }})
                    + ' ' + tz;
    el.textContent = formatted;
  }});

</script>
</body>
</html>"""


# ── Page card ─────────────────────────────────────────────────────────────────

def _render_page(result: dict) -> str:
    url     = result["url"]
    path    = result["path"]
    seo     = result["seo"]
    safe_id = path.strip("/").replace("/", "_") or "home"

    fail_count = seo["fail_count"]
    warn_count = seo["warn_count"]
    if fail_count:
        seo_badge = f'<span class="badge fail">SEO: {fail_count} issue{"s" if fail_count != 1 else ""}</span>'
    elif warn_count:
        seo_badge = f'<span class="badge warn">SEO: {warn_count} warning{"s" if warn_count != 1 else ""}</span>'
    else:
        seo_badge = ''

    checks      = seo.get("checks", [])
    check_rows  = ""
    for c in checks:
        st   = c["status"]
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(st, "")
        name = c["name"]
        detail = c.get("detail") or ""
        value  = c.get("value") or ""
        value_html = ""
        if name in ("Meta Title", "Meta Description") and value:
            limit = 60 if name == "Meta Title" else 160
            value_html = f'<span class="check-value">{_render_char_highlighted(value, limit)}</span>'
        elif value and value != detail:
            truncated = (value[:100] + "…") if len(value) > 100 else value
            value_html = f'<span class="check-value">{_esc(truncated)}</span>'
        action_pill = ""
        if name == "Image Alt Text" and st == "warn":
            action_pill = ('<a class="check-action-pill" href="https://www.framer.com/marketplace/plugins/assetify-advanced-assets-manager" target="_blank">'
                           '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>'
                           ' Use Assetify in Framer</a>')
        check_rows += f'<div class="check-row {st}"><span class="check-icon">{icon}</span><span class="check-name">{name}</span><span class="check-detail">{_esc(detail)}</span>{value_html}{action_pill}</div>\n'

    return f"""
<div class="page-card" id="page-{safe_id}">
  <div class="page-card-header">
    <div>
      <h3>{path or "/"}</h3>
      <div class="url">{url}</div>
    </div>
    <div style="display:flex;align-items:center;gap:12px">
      {seo_badge}
      <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    </div>
  </div>
  <div class="page-card-body">
    <div class="page-card-body-inner">
      <div class="check-list">{check_rows}</div>
    </div>
  </div>
</div>"""


# ── Site SEO section ──────────────────────────────────────────────────────────

def _render_site_seo_section(site_seo: dict) -> str:
    order  = ["Site Language", "Favicon", "Social Preview Image", "Meta Title", "Meta Description"]
    checks = sorted(site_seo.get("checks", []), key=lambda c: order.index(c["name"]) if c["name"] in order else 99)
    cards  = ""
    for c in checks:
        status = c["status"]
        detail = c["detail"] or ""
        value  = c["value"] or ""
        name   = c["name"]

        extra = ""
        if name == "Favicon" and value:
            extra = f'''<div class="favicon-preview">
              <div class="favicon-bg favicon-bg-white"><img src="{value}" alt="favicon on white bg"></div>
              <div class="favicon-bg favicon-bg-black"><img src="{value}" alt="favicon on black bg"></div>
            </div>'''
        elif name == "Social Preview Image" and value:
            extra = f'<img src="{value}" alt="OG / Social Preview image" loading="lazy" style="width:100%;border-radius:8px;margin-top:6px;object-fit:cover">'
        elif name == "Meta Title" and value:
            highlighted = _render_char_highlighted(value, 60)
            extra = f'<div class="site-check-value" style="color:var(--text)">{highlighted}</div>'
        elif name == "Meta Description" and value:
            highlighted = _render_char_highlighted(value, 160)
            extra = f'<div class="site-check-value" style="color:var(--text)">{highlighted}</div>'
        elif name == "Site Language" and value:
            extra = f'<div class="site-check-value" style="font-size:22px;font-weight:700;color:var(--text);letter-spacing:-0.5px">{value}</div>'
        elif value and value != detail:
            truncated = (value[:100] + "…") if len(value) > 100 else value
            extra = f'<div class="site-check-value">{truncated}</div>'

        if name == "Social Preview Image":
            card_class = "site-check-card og-image-card"
        elif name == "Meta Description":
            card_class = "site-check-card wide-card"
        else:
            card_class = "site-check-card"

        cards += f'''
    <div class="{card_class} {status}">
      <div class="site-check-header">
        <span class="site-check-dot"></span>
        <span class="site-check-name">{name}</span>
      </div>
      <div class="site-check-detail">{detail}</div>
      {extra}
    </div>'''

    return f'''
  <div class="section">
    <div class="section-title"><span class="section-icon">🌐</span> Site-level Checks</div>
    <p class="section-subtitle">
      Checked once for the whole site. Title &amp; description use the same field as page meta in Framer — those are in the per-page table below.
    </p>
    <div class="site-checks-grid">{cards}
    </div>
  </div>'''


# ── Helpers ───────────────────────────────────────────────────────────────────

def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_char_highlighted(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return _esc(text)
    ok   = _esc(text[:max_chars])
    over = _esc(text[max_chars:])
    return f'{ok}<span class="char-over">{over}</span>'


# ── SEO table row ─────────────────────────────────────────────────────────────

def _render_seo_row(result: dict) -> str:
    path   = result["path"] or "/"
    url    = result["url"]
    checks = result["seo"]["checks"]

    cells = ""
    for check in checks:
        status = check["status"]
        detail = check["detail"] or ""
        value  = check["value"] or ""
        icon   = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(status, "")
        name   = check["name"]

        if name == "Meta Title":
            highlighted = _render_char_highlighted(value, 60) if value else f'<span style="color:var(--fail)">Missing</span>'
            cells += f'''<td style="white-space:normal;min-width:180px;max-width:280px">
              <div class="badge {status}" style="margin-bottom:5px">{icon} {detail}</div>
              <div style="font-size:12px;line-height:1.5">{highlighted}</div>
            </td>\n'''
        elif name == "Meta Description":
            highlighted = _render_char_highlighted(value, 160) if value else f'<span style="color:var(--fail)">Missing</span>'
            cells += f'''<td style="white-space:normal;min-width:200px;max-width:380px">
              <div class="badge {status}" style="margin-bottom:5px">{icon} {detail}</div>
              <div style="font-size:12px;line-height:1.5">{highlighted}</div>
            </td>\n'''
        else:
            value_str = str(value)[:80] if value else ""
            tip = (detail + (" — " + value_str if value_str and value_str not in detail else "")).replace('"', "&quot;")
            cells += f'<td><span class="badge {status}" data-tip="{tip}">{icon}</span></td>\n'

    return f"""<tr>
  <td class="page-url"><a href="{url}" target="_blank">{path}</a></td>
  {cells}
</tr>"""
