"""
reporter.py — Generates a self-contained HTML QA report.

The report includes:
  • Summary dashboard (pass rate, issue count)
  • Per-page SEO/meta checklist table
  • Visual comparison section with Live / Figma / Diff tabs per viewport
"""

import os
import json
from datetime import datetime
from modules.comparator import similarity_label, similarity_color


def generate_report(results: list[dict], config: dict, output_dir: str, timestamp: str,
                    site_seo: dict | None = None) -> str:
    """
    Generates the HTML report and returns its file path.
    """
    report_path = os.path.join(output_dir, "report.html")

    site_url    = config["site_url"]
    viewports   = config["viewports"]
    date_str    = datetime.now().strftime("%B %d, %Y at %H:%M")
    total_pages = len(results)

    # Page-level SEO aggregate stats
    total_pass   = sum(r["seo"]["pass_count"] for r in results)
    total_warn   = sum(r["seo"]["warn_count"] for r in results)
    total_fail   = sum(r["seo"]["fail_count"] for r in results)

    # Visual comparison stats
    all_similarities = []
    for r in results:
        for vp_data in r.get("viewports", []):
            if vp_data.get("similarity") is not None:
                all_similarities.append(vp_data["similarity"])
    avg_similarity = sum(all_similarities) / len(all_similarities) if all_similarities else None

    html = _render_html(
        site_url=site_url,
        date_str=date_str,
        total_pages=total_pages,
        total_pass=total_pass,
        total_warn=total_warn,
        total_fail=total_fail,
        avg_similarity=avg_similarity,
        results=results,
        viewports=viewports,
        output_dir=output_dir,
        site_seo=site_seo,
    )

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    return report_path


# ══════════════════════════════════════════════════════════════════════════════
# HTML rendering
# ══════════════════════════════════════════════════════════════════════════════

def _render_html(*, site_url, date_str, total_pages, total_pass, total_warn,
                 total_fail, avg_similarity, results, viewports, output_dir, site_seo=None):

    pages_html = "\n".join(_render_page(r, viewports, output_dir) for r in results)

    # Safe key for localStorage (strip protocol + special chars)
    site_url_safe = site_url.replace("https://", "").replace("http://", "").replace("/", "_").replace(".", "_").replace("-", "_")

    seo_table_rows = "\n".join(_render_seo_row(r) for r in results)
    seo_check_names = []
    for r in results:  # use first result that actually has checks (homepage may fail)
        names = [c["name"] for c in (r.get("seo") or {}).get("checks") or []]
        if names:
            seo_check_names = names
            break
    seo_headers = "\n".join(f"<th>{name}</th>" for name in seo_check_names)

    sim_html = ""
    if avg_similarity is not None:
        color = similarity_color(avg_similarity)
        sim_html = f'<div class="stat-card card-sim"><div class="stat-value neutral">{avg_similarity:.1f}%</div><div class="stat-label">Avg Visual Match</div></div>'

    pass_pct = round(total_pass / max(total_pass + total_fail, 1) * 100)

    site_seo_html = _render_site_seo_section(site_seo) if site_seo else ""

    # Sidebar navigation links for each page
    def _sidebar_page_link(r):
        path    = r.get("path", "/") or "/"
        sid     = path.strip("/").replace("/", "_") or "home"
        label   = path if path != "/" else "/"
        seo     = r.get("seo", {})
        dot_color = "#dc2626" if seo.get("fail_count") else ("#d97706" if seo.get("warn_count") else "#16a34a")
        return (f'<a href="#page-{sid}" class="nav-item">'
                f'<span class="nav-dot" style="background:{dot_color}"></span>'
                f'{label}</a>')
    sidebar_links = "\n".join(_sidebar_page_link(r) for r in results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Framer QA Report — {site_url}</title>
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
    --shadow-sm:    0 1px 3px rgba(16,24,40,.06), 0 1px 2px rgba(16,24,40,.04);
    --shadow:       0 4px 16px rgba(16,24,40,.08), 0 1px 4px rgba(16,24,40,.04);
    --radius:       12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #eaecf0;
    min-height: 100vh;
    padding: 20px;
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
    height: calc(100vh - 40px);
    max-width: 1480px;
    margin: 0 auto;
    background: var(--shell-bg);
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 24px 64px rgba(16,24,40,.10), 0 0 0 1px rgba(16,24,40,.06);
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
    background: var(--accent);
    border-radius: 9px;
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
    flex-shrink: 0;
    cursor: pointer;
    transition: opacity .15s;
    box-shadow: 0 1px 4px rgba(16,24,40,.2);
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
    font-size: 11.5px; font-weight: 500;
    color: var(--accent);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    margin-bottom: 2px;
  }}
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

  /* ── Page title ── */
  .page-heading {{
    margin-bottom: 28px;
  }}
  .page-heading h2 {{
    font-size: 22px; font-weight: 800;
    color: var(--text); letter-spacing: -0.5px;
    margin-bottom: 4px;
  }}
  .page-heading .sub {{
    font-size: 13px; color: var(--muted);
  }}
  .page-heading .sub a {{ color: var(--accent); }}

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
    font-size: 30px; font-weight: 800;
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
    font-size: 11px; font-weight: 700;
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

  /* ── Instant custom tooltip (replaces native title delay) ── */
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
    box-shadow: 0 4px 12px rgba(0,0,0,.25);
    pointer-events: none;
    opacity: 0;
    transition: opacity .1s;
    z-index: 100;
  }}
  .badge[data-tip]:hover::after {{
    opacity: 1;
  }}

  /* ── Page Cards (Visual Comparison) ── */
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
  .page-card.open .chevron {{ transform: rotate(180deg); }}
  .page-card-body {{ display: none; padding: 18px; }}
  .page-card.open .page-card-body {{ display: block; }}

  /* ── Viewport Tabs ── */
  .vp-tabs {{
    display: flex;
    gap: 4px;
    margin-bottom: 16px;
    background: var(--subtle);
    padding: 3px;
    border-radius: 8px;
    width: fit-content;
    border: 1px solid var(--border2);
  }}
  .vp-tab {{
    padding: 4px 13px;
    border-radius: 6px;
    border: none;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: background .15s, color .15s;
    letter-spacing: 0.01em;
    font-family: inherit;
  }}
  .vp-tab:hover {{ color: var(--text); background: rgba(0,0,0,.04); }}
  .vp-tab.active {{
    background: var(--surface);
    color: var(--accent);
    font-weight: 600;
    box-shadow: var(--shadow-sm);
  }}

  .vp-panel {{ display: none; }}
  .vp-panel.active {{ display: block; }}

  /* ── Image Comparison ── */
  .img-view-tabs {{
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
  }}
  .img-tab {{
    padding: 4px 12px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: all .15s;
  }}
  .img-tab:hover {{ border-color: var(--accent); color: var(--accent); }}
  .img-tab.active {{ background: var(--accent-light); border-color: var(--accent); color: var(--accent); font-weight: 600; }}

  .img-panels {{ position: relative; }}
  .img-panel {{ display: none; }}
  .img-panel.active {{ display: block; }}

  .screenshot {{
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 8px;
    display: block;
  }}

  .sim-badge {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 12px;
  }}

  .no-figma {{
    background: var(--subtle);
    border: 1px dashed var(--border);
    border-radius: 8px;
    padding: 32px;
    text-align: center;
    color: var(--muted);
    font-size: 13px;
  }}

  /* ── Tooltip ── */
  [title] {{ cursor: help; }}

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
  }}
  .site-check-card:hover {{ box-shadow: var(--shadow); border-color: #c4c9d4; }}
  .site-check-card.og-image-card {{
    grid-column: span 1;
    grid-row: span 2;
  }}
  .site-check-card.wide-card {{
    grid-column: span 2;
  }}
  @media (max-width: 700px) {{
    .site-checks-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .site-check-card.og-image-card {{ grid-row: span 1; }}
  }}
  @media (max-width: 480px) {{
    .site-checks-grid {{ grid-template-columns: 1fr; }}
    .site-check-card.wide-card,
    .site-check-card.og-image-card {{ grid-column: span 1; grid-row: span 1; }}
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
  /* Favicon swatch */
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
  /* OG image preview */
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
  /* Character over-limit highlight */
  .char-over {{
    color: #dc2626;
    background: #fee2e2;
    border-radius: 2px;
    padding: 0 1px;
  }}

  /* ── Compare Slider ── */
  .compare-container {{
    position: relative;
    overflow: hidden;
    border-radius: 8px;
    border: 1px solid var(--border);
    cursor: col-resize;
    user-select: none;
    -webkit-user-select: none;
  }}
  .compare-base {{
    width: 100%;
    display: block;
  }}
  .compare-top {{
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    display: block;
    clip-path: inset(0 50% 0 0);
    pointer-events: none;
  }}
  .compare-line {{
    position: absolute;
    top: 0; left: 50%;
    transform: translateX(-50%);
    width: 2px;
    height: 100%;
    background: #fff;
    box-shadow: 0 0 6px rgba(0,0,0,.45);
    pointer-events: none;
  }}
  .compare-knob {{
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 38px; height: 38px;
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 2px 10px rgba(0,0,0,.3);
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
    z-index: 10;
  }}
  .compare-label {{
    position: absolute;
    bottom: 10px;
    background: rgba(0,0,0,.55);
    color: #fff;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: .4px;
    padding: 3px 9px;
    border-radius: 4px;
    pointer-events: none;
    text-transform: uppercase;
  }}

  /* ── CSS Annotations ── */
  .annotations {{
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .ann-title {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: var(--muted);
    margin-bottom: 2px;
  }}
  .ann-item {{
    display: flex;
    gap: 10px;
    align-items: flex-start;
    background: var(--subtle);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 12.5px;
  }}
  .ann-badge {{
    flex-shrink: 0;
    width: 22px; height: 22px;
    border-radius: 50%;
    background: #fb923c;
    color: #fff;
    font-weight: 700;
    font-size: 11px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 1px;
  }}
  .ann-body {{ flex: 1; min-width: 0; }}
  .ann-selector {{
    font-family: 'SFMono-Regular', 'Consolas', monospace;
    font-size: 12px;
    color: var(--accent);
    font-weight: 600;
    margin-bottom: 4px;
  }}
  .ann-text {{
    color: var(--muted);
    font-size: 11.5px;
    margin-bottom: 5px;
    font-style: italic;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .ann-props {{
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }}
  .ann-prop {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 7px;
    font-size: 11px;
    font-family: 'SFMono-Regular', 'Consolas', monospace;
    color: var(--text);
    white-space: nowrap;
  }}
  .ann-prop span {{ color: var(--muted); }}

  /* ── Footer ── */
  .footer {{
    border-top: 1px solid var(--border2);
    padding: 16px 44px;
    color: var(--muted2);
    font-size: 11px;
    text-align: center;
    letter-spacing: .1px;
  }}

  /* ── Per-page notes ── */
  .page-notes-wrapper {{
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
  }}
  .page-notes-label {{
    font-size: 11.5px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: .5px;
    margin-bottom: 6px;
  }}
  .page-notes {{
    min-height: 64px;
    padding: 10px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--subtle);
    font-size: 13px;
    color: var(--text);
    outline: none;
    line-height: 1.6;
    font-family: inherit;
    transition: border-color .15s, background .15s;
  }}
  .page-notes:focus {{ border-color: var(--accent); background: #ffffff; }}
  .page-notes:empty:before {{
    content: attr(data-placeholder);
    color: var(--muted);
    pointer-events: none;
  }}

  /* ── Print media ── */
  @media print {{
    body {{ background: white !important; padding: 0; }}
    .app-shell {{ height: auto; box-shadow: none; border-radius: 0; display: block; }}
    .sidebar {{ display: none !important; }}
    .main-content {{ overflow: visible; }}
    .main-inner {{ padding: 24px; max-width: 100%; }}
    .sidebar-btn {{ display: none !important; }}
    .vp-tabs, .img-view-tabs {{ display: none !important; }}
    .page-card-body {{ display: block !important; }}
    .page-card {{ break-inside: avoid; margin-bottom: 24px; box-shadow: none; }}
    .vp-panel {{ display: block !important; }}
    .img-panel {{ display: block !important; margin-bottom: 8px; }}
    .screenshot {{ max-height: 400px; object-fit: contain; }}
    .stat-card {{ break-inside: avoid; print-color-adjust: exact; -webkit-print-color-adjust: exact; }}
    .summary {{ grid-template-columns: repeat(4, 1fr); }}
    .page-notes-wrapper {{ display: none; }}
    .site-checks-grid {{ grid-template-columns: repeat(3, 1fr); }}
  }}
</style>
</head>
<body>

<div class="app-shell">

  <!-- ── Sidebar ── -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-logo" onclick="window.location.href='/'" title="Back to Framer QA">🔍</div>
      <span class="sidebar-brand-name">Framer QA</span>
    </div>
    <div class="sidebar-meta">
      <div class="sidebar-site"><a href="{site_url}" target="_blank" style="color:var(--accent);text-decoration:none">{site_url}</a></div>
      <div class="sidebar-date">{date_str}</div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section-label">Report</div>
      <a href="#summary" class="nav-item"><span class="nav-item-icon">📊</span> Overview</a>
      <a href="#site-checks" class="nav-item"><span class="nav-item-icon">🌐</span> Site Checks</a>
      <a href="#seo-table" class="nav-item"><span class="nav-item-icon">📋</span> Page SEO</a>
      <a href="#visual" class="nav-item"><span class="nav-item-icon">🎨</span> Visual</a>
      <div class="nav-section-label">Pages</div>
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

      <!-- Page heading -->
      <div class="page-heading" id="summary">
        <h2>QA Report</h2>
        <div class="sub">{total_pages} page{"s" if total_pages != 1 else ""} checked &nbsp;·&nbsp; {date_str}</div>
      </div>

      <!-- Summary Cards -->
      <div class="summary">
        <div class="stat-card card-neutral">
          <div class="stat-value neutral">{total_pages}</div>
          <div class="stat-label">Pages Checked</div>
        </div>
        <div class="stat-card card-pass">
          <div class="stat-value pass">{total_pass}</div>
          <div class="stat-label">SEO Passed</div>
        </div>
        <div class="stat-card card-warn">
          <div class="stat-value warn">{total_warn}</div>
          <div class="stat-label">Warnings</div>
        </div>
        <div class="stat-card card-fail">
          <div class="stat-value fail">{total_fail}</div>
          <div class="stat-label">Failures</div>
        </div>
        {sim_html}
      </div>

      <!-- Site-level SEO -->
      <div id="site-checks">
        {site_seo_html}
      </div>

      <!-- Page-level SEO Table -->
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

      <!-- Visual Comparison -->
      <div class="section" id="visual">
        <div class="section-title"><span class="section-icon">🎨</span> Visual Comparison — Live vs Figma</div>
        {pages_html}
      </div>

      <div class="footer">Framer QA &nbsp;·&nbsp; {date_str}</div>

    </div>
  </main>

</div>

<script>
  // Copy shareable link
  function copyReportLink(btn) {{
    // If inside an iframe, build the full URL from the parent
    const url = window.self !== window.top
      ? window.location.href
      : window.location.href;
    navigator.clipboard.writeText(url).then(() => {{
      const orig = btn.innerHTML;
      btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> Copied!';
      btn.style.color = '#10b981';
      setTimeout(() => {{ btn.innerHTML = orig; btn.style.color = ''; }}, 2000);
    }}).catch(() => {{
      // Fallback for browsers that block clipboard in iframes
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

  // Save as PDF
  function savePDF() {{
    // Expand all cards first so nothing is clipped in the PDF
    document.querySelectorAll('.page-card').forEach(c => c.classList.add('open'));
    if (window.self !== window.top) {{
      // Inside an iframe — open in new tab with ?autoprint=1 so it prints automatically
      const sep = window.location.href.includes('?') ? '&' : '?';
      window.open(window.location.href + sep + 'autoprint=1', '_blank');
    }} else {{
      window.print();
    }}
  }}

  // Auto-print if ?autoprint=1 is in the URL (triggered from iframe)
  if (new URLSearchParams(window.location.search).get('autoprint') === '1') {{
    document.querySelectorAll('.page-card').forEach(c => c.classList.add('open'));
    window.addEventListener('load', () => setTimeout(() => window.print(), 800));
  }}

  // Sidebar scroll-spy — highlight nav item matching the nearest section
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

  // Page card accordion
  document.querySelectorAll('.page-card-header').forEach(header => {{
    header.addEventListener('click', () => {{
      const card = header.closest('.page-card');
      card.classList.toggle('open');
    }});
  }});

  // Viewport tabs — event delegation so tabs in collapsed cards work on open
  document.addEventListener('click', e => {{
    const tab = e.target.closest('.vp-tab');
    if (!tab) return;
    const vpTabs = tab.closest('.vp-tabs');
    if (!vpTabs) return;
    const group = vpTabs.dataset.group;
    document.querySelectorAll(`[data-group="${{group}}"].vp-tab`)
      .forEach(t => t.classList.remove('active'));
    document.querySelectorAll(`[data-group="${{group}}"].vp-panel`)
      .forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = document.querySelector(`[data-group="${{group}}"][data-vp="${{tab.dataset.vp}}"].vp-panel`);
    if (target) target.classList.add('active');
  }});

  // Image view tabs — event delegation so tabs in collapsed/inactive panels work correctly
  document.addEventListener('click', e => {{
    const tab = e.target.closest('.img-tab');
    if (!tab) return;
    const viewTabs = tab.closest('.img-view-tabs');
    if (!viewTabs) return;
    const group = viewTabs.dataset.group;
    document.querySelectorAll(`[data-group="${{group}}"].img-tab`)
      .forEach(t => t.classList.remove('active'));
    document.querySelectorAll(`[data-group="${{group}}"].img-panel`)
      .forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const target = document.querySelector(`[data-group="${{group}}"][data-view="${{tab.dataset.view}}"].img-panel`);
    if (target) target.classList.add('active');
  }});

  // Open first page card by default
  const firstCard = document.querySelector('.page-card');
  if (firstCard) firstCard.classList.add('open');

  // ── Compare sliders (Live vs Figma) ──────────────────────────────────────
  const mainScroll = document.querySelector('.main-content') || window;

  document.querySelectorAll('.compare-container').forEach(container => {{
    const topImg  = container.querySelector('.compare-top');
    const line    = container.querySelector('.compare-line');
    const knob    = container.querySelector('.compare-knob');
    let dragging  = false;

    function update(clientX) {{
      const rect = container.getBoundingClientRect();
      const pct  = Math.max(1, Math.min(99, (clientX - rect.left) / rect.width * 100));
      topImg.style.clipPath = `inset(0 ${{100 - pct}}% 0 0)`;
      line.style.left       = `${{pct}}%`;
      knob.style.left       = `${{pct}}%`;
    }}

    // Keep knob vertically centered in the visible portion of the container
    function updateKnobY() {{
      const cRect   = container.getBoundingClientRect();
      const scrollEl = (mainScroll === window) ? document.documentElement : mainScroll;
      const viewTop  = (mainScroll === window) ? 0 : mainScroll.getBoundingClientRect().top;
      const viewBot  = (mainScroll === window) ? window.innerHeight : mainScroll.getBoundingClientRect().bottom;
      const visTop   = Math.max(cRect.top,    viewTop);
      const visBot   = Math.min(cRect.bottom, viewBot);
      if (visBot <= visTop) return;
      // Convert viewport-relative center to container-relative top
      const centerInContainer = (visTop + visBot) / 2 - cRect.top;
      knob.style.top       = centerInContainer + 'px';
      knob.style.transform = 'translateX(-50%)';
    }}

    mainScroll.addEventListener('scroll', updateKnobY, {{passive: true}});
    window.addEventListener('resize', updateKnobY);
    updateKnobY();

    container.addEventListener('mousedown',  e => {{ dragging = true;  update(e.clientX); e.preventDefault(); }});
    window.addEventListener   ('mousemove',  e => {{ if (dragging) update(e.clientX); }});
    window.addEventListener   ('mouseup',    ()  => {{ dragging = false; }});
    container.addEventListener('touchstart', e => {{ dragging = true;  update(e.touches[0].clientX); }}, {{passive: true}});
    window.addEventListener   ('touchmove',  e => {{ if (dragging) update(e.touches[0].clientX); }},    {{passive: true}});
    window.addEventListener   ('touchend',   ()  => {{ dragging = false; }});
  }});

  // Per-page notes — persisted in localStorage
  const NOTES_KEY = 'framerqa_notes_{site_url_safe}';
  function loadNotes() {{
    try {{ return JSON.parse(localStorage.getItem(NOTES_KEY) || '{{}}'); }} catch {{ return {{}}; }}
  }}
  function saveNotes(notes) {{
    try {{ localStorage.setItem(NOTES_KEY, JSON.stringify(notes)); }} catch {{}}
  }}
  document.querySelectorAll('.page-notes').forEach(el => {{
    const page = el.dataset.page;
    const notes = loadNotes();
    if (notes[page]) el.innerHTML = notes[page];
    el.addEventListener('input', () => {{
      const n = loadNotes();
      n[page] = el.innerHTML;
      saveNotes(n);
    }});
  }});
</script>
</body>
</html>"""


# ── Page card ─────────────────────────────────────────────────────────────────

def _render_page(result: dict, viewports: list[dict], output_dir: str) -> str:
    url       = result["url"]
    path      = result["path"]
    seo       = result["seo"]
    vp_data   = result.get("viewports", [])
    safe_id   = path.strip("/").replace("/", "_") or "home"

    # Build viewport tabs + panels
    vp_tabs   = ""
    vp_panels = ""
    group_id  = f"vp_{safe_id}"

    for i, vp_result in enumerate(vp_data):
        vp     = vp_result["viewport"]
        active = "active" if i == 0 else ""
        vp_tabs += f'<button class="vp-tab {active}" data-group="{group_id}" data-vp="{i}">{vp["name"]} <span style="color:var(--muted);font-weight:400">({vp["width"]}px)</span></button>\n'
        vp_panels += _render_vp_panel(vp_result, i, group_id, safe_id, active, output_dir, vp_result.get("annotations") or [])

    # SEO mini-summary
    fail_count = seo["fail_count"]
    warn_count = seo["warn_count"]
    seo_badge  = ""
    if fail_count:
        seo_badge = f'<span class="badge fail">SEO: {fail_count} issue{"s" if fail_count != 1 else ""}</span>'
    elif warn_count:
        seo_badge = f'<span class="badge warn">SEO: {warn_count} warning{"s" if warn_count != 1 else ""}</span>'
    else:
        seo_badge = ''

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
    <div class="vp-tabs" data-group="{group_id}">
      {vp_tabs}
    </div>
    {vp_panels}
    <div class="page-notes-wrapper">
      <div class="page-notes-label">📝 Notes</div>
      <div class="page-notes" contenteditable="true" data-page="{safe_id}" data-placeholder="Add QA notes for this page…"></div>
    </div>
  </div>
</div>"""


def _render_vp_panel(vp_result: dict, idx: int, group_id: str, safe_id: str, active: str, output_dir: str, annotations: list = []) -> str:
    vp          = vp_result["viewport"]
    live_path   = vp_result.get("live_path")
    figma_path  = vp_result.get("figma_path")
    diff_path   = vp_result.get("diff_path")
    similarity  = vp_result.get("similarity")
    view_group  = f"{group_id}_{idx}"

    # Relative image paths from the report HTML location
    def rel_path(p):
        if p and os.path.exists(p):
            return os.path.relpath(p, output_dir)
        return None

    live_rel  = rel_path(live_path)
    figma_rel = rel_path(figma_path)
    diff_rel  = rel_path(diff_path)

    if not live_rel:
        return f'<div class="vp-panel {active}" data-group="{group_id}" data-vp="{idx}"><div class="no-figma">Screenshot not available</div></div>'

    has_figma   = figma_rel is not None
    has_diff    = diff_rel is not None

    sim_badge = ""
    if similarity is not None:
        color = similarity_color(similarity)
        label = similarity_label(similarity)
        sim_badge = f'<div class="sim-badge badge {color}">{similarity:.1f}% — {label}</div>'

    # When Figma is available, Compare slider is the default tab.
    # When Figma is not available, Live is the default (no slider).
    default_view = "compare" if has_figma else "live"

    img_tabs = ""
    img_panels = ""

    if has_figma:
        # Compare slider tab (default)
        img_tabs += f'<button class="img-tab active" data-group="{view_group}" data-view="compare">⇔ Compare</button>\n'
        knob_svg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#374151" stroke-width="2.5"><line x1="3" y1="12" x2="21" y2="12"/><polyline points="8 7 3 12 8 17"/><polyline points="16 7 21 12 16 17"/></svg>'
        img_panels += f'''<div class="img-panel active" data-group="{view_group}" data-view="compare">
  <div class="compare-container">
    <img class="compare-base" src="{figma_rel}" alt="Figma design" loading="lazy">
    <img class="compare-top"  src="{live_rel}"  alt="Live site"    loading="lazy">
    <div class="compare-line"></div>
    <div class="compare-knob">{knob_svg}</div>
    <div class="compare-label" style="left:10px">Live</div>
    <div class="compare-label" style="right:10px">Figma</div>
  </div>
</div>\n'''
        # Live tab
        img_tabs  += f'<button class="img-tab" data-group="{view_group}" data-view="live">Live</button>\n'
        img_panels += f'<div class="img-panel" data-group="{view_group}" data-view="live"><img class="screenshot" src="{live_rel}" alt="Live screenshot" loading="lazy"></div>\n'
        # Figma tab
        img_tabs  += f'<button class="img-tab" data-group="{view_group}" data-view="figma">Figma</button>\n'
        img_panels += f'<div class="img-panel" data-group="{view_group}" data-view="figma"><img class="screenshot" src="{figma_rel}" alt="Figma export" loading="lazy"></div>\n'
    else:
        # No Figma — just show Live
        img_tabs  += f'<button class="img-tab active" data-group="{view_group}" data-view="live">Live</button>\n'
        img_panels += f'<div class="img-panel active" data-group="{view_group}" data-view="live"><img class="screenshot" src="{live_rel}" alt="Live screenshot" loading="lazy"></div>\n'

    if has_diff:
        img_tabs  += f'<button class="img-tab" data-group="{view_group}" data-view="diff">Diff</button>\n'
        annotations_html = _render_annotations(annotations)
        img_panels += f'<div class="img-panel" data-group="{view_group}" data-view="diff"><img class="screenshot" src="{diff_rel}" alt="Pixel diff" loading="lazy">{annotations_html}</div>\n'

    return f"""
<div class="vp-panel {active}" data-group="{group_id}" data-vp="{idx}">
  {sim_badge}
  <div class="img-view-tabs" data-group="{view_group}">{img_tabs}</div>
  <div class="img-panels">
    {img_panels}
  </div>
</div>"""


# ── CSS Annotations ───────────────────────────────────────────────────────────

def _render_annotations(annotations: list) -> str:
    """Renders the numbered CSS annotation list shown below the diff image."""
    if not annotations:
        return ""

    items = ""
    for a in annotations:
        selector = _esc(a.get("selector") or "?")
        text     = a.get("text") or ""
        styles   = a.get("styles") or {}
        num      = a.get("index", "?")

        text_html = f'<div class="ann-text">"{_esc(text[:60])}"</div>' if text else ""

        props_html = "".join(
            f'<span class="ann-prop"><span>{_esc(k)}: </span>{_esc(str(v))}</span>'
            for k, v in styles.items()
        )

        items += f"""
<div class="ann-item">
  <div class="ann-badge">{num}</div>
  <div class="ann-body">
    <div class="ann-selector">{selector}</div>
    {text_html}
    <div class="ann-props">{props_html}</div>
  </div>
</div>"""

    return f'<div class="annotations"><div class="ann-title">🔬 Changed regions — live CSS</div>{items}</div>'


# ── Site SEO section ──────────────────────────────────────────────────────────

def _render_site_seo_section(site_seo: dict) -> str:
    """Renders a card-style section for site-level SEO checks (lang, favicon, OG, Twitter)."""
    checks   = site_seo.get("checks", [])

    cards = ""
    for c in checks:
        status = c["status"]
        detail = c["detail"] or ""
        value  = c["value"] or ""
        name   = c["name"]

        # Extra content per check type
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

        # Card layout: OG image = 1 col but spans 2 rows, Meta Description = 2 cols, rest = 1 col
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


# ── Character highlight helper ────────────────────────────────────────────────

def _esc(s: str) -> str:
    """Minimal HTML escape."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_char_highlighted(text: str, max_chars: int) -> str:
    """Returns HTML where characters beyond max_chars are wrapped in a red highlight span."""
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
