# Framer QA

Automated QA tool for Framer websites. Checks every page against your Figma designs and validates SEO/meta tags — accessible via a web UI that anyone on your team can use.

---

## Web App (recommended)

### Option A — Docker (easiest for servers)

```bash
git clone <your-repo>
cd framer-qa

# Edit SECRET_KEY in docker-compose.yml first!
docker compose up -d
```

Open `http://your-server:8080` in your browser.

### Option B — Run directly with Python

**Requirements:** Python 3.11+

```bash
pip install -r requirements.txt
playwright install chromium --with-deps

# Development
python app.py

# Production (gunicorn)
gunicorn -w 2 --threads 4 -b 0.0.0.0:8080 --timeout 300 "app:app"
```

Open `http://localhost:5000` (dev) or `http://your-server:8080` (prod).

---

## Using the web UI

1. **Site URL** — enter your Framer site URL (required)
2. **Figma** (optional) — paste your API token and file ID, then click **Fetch frames** to auto-discover all your Figma frames
3. **Page mappings** — click a frame from the list, or manually add URL path → Node ID pairs
4. **Viewports** — adjust widths to match your Framer breakpoints
5. Click **Run QA Check** — live logs stream in the right panel
6. When done, click **Open Report** — view inline or open in a new tab

---

## Command-line mode

The original CLI is still available:

```bash
# Configure config.json first, then:
python qa_agent.py              # Full QA (all pages)
python qa_agent.py --seo-only  # SEO checks only
python qa_agent.py --url /about # Single page
python qa_agent.py --list-frames # Discover Figma node IDs
```

---

## What it checks

**SEO & Meta (every page)**
- Meta title (10–60 chars recommended)
- Meta description (50–160 chars recommended)
- Site language (`html[lang]` attribute)
- Favicon (reachability check)
- Canonical URL
- Open Graph: `og:title`, `og:description`, `og:image`
- Twitter Card
- Robots meta tag

**Visual comparison**
- Full-page screenshots at Desktop / Tablet / Mobile (configurable)
- Pixel-diff vs Figma exports with similarity score
- Diff image highlights changed pixels in red

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | Server port |
| `SECRET_KEY` | dev key | Flask secret — **change in production** |
| `MAX_JOBS` | `3` | Max concurrent QA runs |
| `JOB_TTL_HOURS` | `24` | Hours to keep reports before cleanup |

---

## Finding Figma node IDs

1. Open your Figma file
2. Click a top-level frame
3. Look at the URL: `...?node-id=123-456`
4. Use `123:456` as the node ID (replace `-` with `:`)

Or use the **Fetch frames** button in the UI — it lists all frames with their IDs automatically.

---

## Visual diff interpretation

| Score | Status |
|---|---|
| 98–100% | ✅ Pixel-perfect |
| 90–97% | ⚠️ Minor differences |
| 70–89% | ⚠️ Noticeable differences |
| < 70% | ❌ Major differences |

---

## Security note

Figma API tokens entered in the web UI are sent to the server and used only for that check — they are not stored or logged. For a public-facing deployment, consider adding authentication in front of the app (e.g. HTTP Basic Auth in nginx, or Cloudflare Access).
