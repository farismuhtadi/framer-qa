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

    seo_table_rows = "\n".join(_render_seo_row(r) for r in results)
    seo_check_names = []
    if results:
        seo_check_names = [c["name"] for c in results[0]["seo"]["checks"]]
    seo_headers = "\n".join(f"<th>{name}</th>" for name in seo_check_names)

    sim_html = ""
    if avg_similarity is not None:
        color = similarity_color(avg_similarity)
        sim_html = f'<div class="stat-card"><div class="stat-value {color}">{avg_similarity:.1f}%</div><div class="stat-label">Avg Visual Match</div></div>'

    pass_pct = round(total_pass / max(total_pass + total_fail, 1) * 100)

    site_seo_html = _render_site_seo_section(site_seo) if site_seo else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Framer QA Report — {site_url}</title>
<style>
  :root {{
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --border:   #2a2d3a;
    --text:     #e4e6f0;
    --muted:    #7c7f96;
    --pass:     #34c759;
    --warn:     #ff9f0a;
    --fail:     #ff3b30;
    --accent:   #5e6ad2;
    --radius:   12px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    font-size: 14px;
    line-height: 1.6;
  }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  /* ── Layout ── */
  .header {{
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 28px 40px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .header-left h1 {{ font-size: 20px; font-weight: 700; }}
  .header-left .subtitle {{ color: var(--muted); font-size: 13px; margin-top: 4px; }}
  .header-right {{ color: var(--muted); font-size: 13px; text-align: right; }}

  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 40px; }}

  /* ── Summary Cards ── */
  .summary {{
    display: flex;
    gap: 16px;
    margin-bottom: 40px;
    flex-wrap: wrap;
  }}
  .stat-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px 28px;
    flex: 1;
    min-width: 140px;
    text-align: center;
  }}
  .stat-value {{
    font-size: 32px;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 6px;
  }}
  .stat-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }}
  .pass   {{ color: var(--pass); }}
  .warn   {{ color: var(--warn); }}
  .fail   {{ color: var(--fail); }}
  .neutral {{ color: var(--text); }}

  /* ── Section ── */
  .section {{ margin-bottom: 48px; }}
  .section-title {{
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 20px;
    padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }}

  /* ── SEO Table ── */
  .table-wrap {{ overflow-x: auto; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  th, td {{
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
  }}
  th {{
    background: var(--surface);
    color: var(--muted);
    font-weight: 600;
    text-align: left;
    position: sticky;
    top: 0;
  }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  .page-url {{ color: var(--accent); font-weight: 500; }}

  .badge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
  }}
  .badge.pass {{ background: rgba(52,199,89,.15); color: var(--pass); }}
  .badge.warn {{ background: rgba(255,159,10,.15); color: var(--warn); }}
  .badge.fail {{ background: rgba(255,59,48,.15); color: var(--fail); }}

  /* ── Page Cards (Visual Comparison) ── */
  .page-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 24px;
    overflow: hidden;
  }}
  .page-card-header {{
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    cursor: pointer;
    user-select: none;
  }}
  .page-card-header:hover {{ background: rgba(255,255,255,0.03); }}
  .page-card-header h3 {{ font-size: 15px; font-weight: 600; }}
  .page-card-header .url {{ color: var(--muted); font-size: 12px; margin-top: 2px; }}
  .chevron {{ color: var(--muted); transition: transform .2s; }}
  .page-card.open .chevron {{ transform: rotate(180deg); }}
  .page-card-body {{ display: none; padding: 20px; }}
  .page-card.open .page-card-body {{ display: block; }}

  /* ── Viewport Tabs ── */
  .vp-tabs {{
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
  }}
  .vp-tab {{
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: all .15s;
  }}
  .vp-tab:hover {{ border-color: var(--accent); color: var(--text); }}
  .vp-tab.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}

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
  .img-tab:hover {{ border-color: var(--text); color: var(--text); }}
  .img-tab.active {{ background: var(--surface); border-color: var(--text); color: var(--text); }}

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
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 12px;
  }}

  .no-figma {{
    background: rgba(124,127,150,.1);
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
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
  }}
  .site-check-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
  }}
  .site-check-card.og-image-card {{
    grid-column: span 2;
  }}
  .site-check-header {{
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 5px;
  }}
  .site-check-icon {{ font-size: 15px; flex-shrink: 0; }}
  .site-check-name {{ font-weight: 600; font-size: 13px; }}
  .site-check-card.pass .site-check-name {{ color: var(--pass); }}
  .site-check-card.warn .site-check-name {{ color: var(--warn); }}
  .site-check-card.fail .site-check-name {{ color: var(--fail); }}
  .site-check-detail {{ color: var(--muted); font-size: 12px; line-height: 1.5; }}
  .site-check-value {{
    margin-top: 7px;
    font-size: 11px;
    color: var(--muted);
    word-break: break-all;
    line-height: 1.5;
  }}
  /* Favicon swatch */
  .favicon-preview {{
    display: flex;
    gap: 8px;
    margin-top: 10px;
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
  .favicon-bg-white {{ background: #ffffff; }}
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
    color: var(--fail);
    background: rgba(255,59,48,.18);
    border-radius: 2px;
    padding: 0 1px;
  }}

  /* ── Footer ── */
  .footer {{
    border-top: 1px solid var(--border);
    padding: 20px 40px;
    color: var(--muted);
    font-size: 12px;
    text-align: center;
  }}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>🔍 Framer QA Report</h1>
    <div class="subtitle"><a href="{site_url}" target="_blank">{site_url}</a></div>
  </div>
  <div class="header-right">
    Generated {date_str}<br>
    {total_pages} page{"s" if total_pages != 1 else ""} checked
  </div>
</div>

<div class="container">

  <!-- Summary -->
  <div class="summary">
    <div class="stat-card">
      <div class="stat-value neutral">{total_pages}</div>
      <div class="stat-label">Pages Checked</div>
    </div>
    <div class="stat-card">
      <div class="stat-value pass">{total_pass}</div>
      <div class="stat-label">SEO Checks Passed</div>
    </div>
    <div class="stat-card">
      <div class="stat-value warn">{total_warn}</div>
      <div class="stat-label">Warnings</div>
    </div>
    <div class="stat-card">
      <div class="stat-value fail">{total_fail}</div>
      <div class="stat-label">Failures</div>
    </div>
    {sim_html}
  </div>

  {site_seo_html}

  <!-- SEO Checks Table -->
  <div class="section">
    <div class="section-title">📋 Page-level SEO</div>
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
  <div class="section">
    <div class="section-title">🎨 Visual Comparison — Live vs Figma</div>
    {pages_html}
  </div>

</div>

<div class="footer">
  Framer QA Agent &nbsp;·&nbsp; Report generated {date_str}
</div>

<script>
  // Page card accordion
  document.querySelectorAll('.page-card-header').forEach(header => {{
    header.addEventListener('click', () => {{
      const card = header.closest('.page-card');
      card.classList.toggle('open');
    }});
  }});

  // Viewport tabs
  document.querySelectorAll('.vp-tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      const group = tab.closest('.vp-tabs').dataset.group;
      document.querySelectorAll(`[data-group="${{group}}"].vp-tab`)
        .forEach(t => t.classList.remove('active'));
      document.querySelectorAll(`[data-group="${{group}}"].vp-panel`)
        .forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.querySelector(`[data-group="${{group}}"][data-vp="${{tab.dataset.vp}}"].vp-panel`)
        .classList.add('active');
    }});
  }});

  // Image view tabs (Live / Figma / Diff)
  document.querySelectorAll('.img-tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      const group = tab.closest('.img-view-tabs').dataset.group;
      document.querySelectorAll(`[data-group="${{group}}"].img-tab`)
        .forEach(t => t.classList.remove('active'));
      document.querySelectorAll(`[data-group="${{group}}"].img-panel`)
        .forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      document.querySelector(`[data-group="${{group}}"][data-view="${{tab.dataset.view}}"].img-panel`)
        .classList.add('active');
    }});
  }});

  // Open first page card by default
  const firstCard = document.querySelector('.page-card');
  if (firstCard) firstCard.classList.add('open');
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
        vp_panels += _render_vp_panel(vp_result, i, group_id, safe_id, active, output_dir)

    # SEO mini-summary
    fail_count = seo["fail_count"]
    warn_count = seo["warn_count"]
    seo_badge  = ""
    if fail_count:
        seo_badge = f'<span class="badge fail">{fail_count} issue{"s" if fail_count != 1 else ""}</span>'
    elif warn_count:
        seo_badge = f'<span class="badge warn">{warn_count} warning{"s" if warn_count != 1 else ""}</span>'
    else:
        seo_badge = '<span class="badge pass">SEO OK</span>'

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
  </div>
</div>"""


def _render_vp_panel(vp_result: dict, idx: int, group_id: str, safe_id: str, active: str, output_dir: str) -> str:
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

    # Image switcher tabs
    has_figma   = figma_rel is not None
    has_diff    = diff_rel is not None

    sim_badge = ""
    if similarity is not None:
        color = similarity_color(similarity)
        label = similarity_label(similarity)
        sim_badge = f'<div class="sim-badge badge {color}">{similarity:.1f}% — {label}</div>'

    img_tabs  = f'<button class="img-tab active" data-group="{view_group}" data-view="live">Live</button>\n'
    img_live  = f'<div class="img-panel active" data-group="{view_group}" data-view="live"><img class="screenshot" src="{live_rel}" alt="Live screenshot" loading="lazy"></div>'
    img_figma = ""
    img_diff  = ""

    if has_figma:
        img_tabs  += f'<button class="img-tab" data-group="{view_group}" data-view="figma">Figma</button>\n'
        img_figma  = f'<div class="img-panel" data-group="{view_group}" data-view="figma"><img class="screenshot" src="{figma_rel}" alt="Figma export" loading="lazy"></div>'

    if has_diff:
        img_tabs += f'<button class="img-tab" data-group="{view_group}" data-view="diff">Diff</button>\n'
        img_diff  = f'<div class="img-panel" data-group="{view_group}" data-view="diff"><img class="screenshot" src="{diff_rel}" alt="Pixel diff" loading="lazy"></div>'

    no_figma_msg = ""
    if not has_figma:
        no_figma_msg = f'<div class="no-figma" style="margin-top:12px">No Figma frame mapped for this page.<br>Add a node ID to <code>config.json → figma.page_frames</code> to enable comparison.</div>'

    return f"""
<div class="vp-panel {active}" data-group="{group_id}" data-vp="{idx}">
  {sim_badge}
  <div class="img-view-tabs" data-group="{view_group}">{img_tabs}</div>
  <div class="img-panels">
    {img_live}
    {img_figma}
    {img_diff}
  </div>
  {no_figma_msg}
</div>"""


# ── Site SEO section ──────────────────────────────────────────────────────────

def _render_site_seo_section(site_seo: dict) -> str:
    """Renders a card-style section for site-level SEO checks (lang, favicon, OG, Twitter)."""
    checks   = site_seo.get("checks", [])
    icon_map = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

    cards = ""
    for c in checks:
        status = c["status"]
        icon   = icon_map.get(status, "")
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
            extra = f'<div class="og-image-preview"><img src="{value}" alt="OG / Social Preview image" loading="lazy"></div>'
        elif value:
            truncated = (value[:100] + "…") if len(value) > 100 else value
            extra = f'<div class="site-check-value">{truncated}</div>'

        # Social Preview image card spans 2 columns for the wider image
        card_class = "site-check-card og-image-card" if name == "Social Preview Image" else "site-check-card"

        cards += f'''
    <div class="{card_class} {status}">
      <div class="site-check-header">
        <span class="site-check-icon">{icon}</span>
        <span class="site-check-name">{name}</span>
      </div>
      <div class="site-check-detail">{detail}</div>
      {extra}
    </div>'''

    return f'''
  <div class="section">
    <div class="section-title">🌐 Site-level Checks</div>
    <p style="color:var(--muted);font-size:13px;margin-bottom:16px">
      Checked once for the whole site. In Framer, title &amp; description come from the same field as the page meta — those are in the per-page table below.
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
            tip = (detail + (" — " + value[:80] if value else "")).replace('"', "&quot;")
            cells += f'<td><span class="badge {status}" title="{tip}">{icon}</span></td>\n'

    return f"""<tr>
  <td class="page-url"><a href="{url}" target="_blank">{path}</a></td>
  {cells}
</tr>"""
