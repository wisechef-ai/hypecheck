# HypeCheck API + Landing Page Spec

## 1. FastAPI Backend (`api/`)

Create `api/` directory with a FastAPI app that wraps the existing pipeline.

### Endpoints

**POST /api/hypecheck/check**
- Body: `{ "urls": ["https://x.com/..."], "full": false }`
- Returns the pipeline output as JSON
- Rate limit: 3 checks/day per IP for unauthenticated, unlimited for API key holders
- If `full: true`, includes full_stage_output

**GET /api/hypecheck/report/{report_id}**
- Returns a saved report by ID

**GET /api/hypecheck/health**
- Returns `{ "status": "ok", "version": "0.2.0" }`

### Auth
- Optional `X-API-Key` header
- If no key: rate limited to 3 checks/day per IP (use simple in-memory dict with TTL)
- If valid key: unlimited (for now, keys are just strings in an env var `HYPECHECK_API_KEYS=key1,key2,key3`)

### File: `api/main.py`
- Use FastAPI + uvicorn
- Import and call `run_pipeline` from `src.pipeline`
- CORS enabled (allow all origins for now)
- Serve on port 3347

### File: `api/requirements.txt`
- fastapi>=0.115.0
- uvicorn[standard]>=0.34.0
- (inherit main project deps)

## 2. Landing Page (`landing/`)

Create `landing/` directory with a single-page app for wisechef.ai/hypecheck

### File: `landing/index.html`
A clean, modern single page:

**Hero section:**
- Title: "HypeCheck" with a shield/magnifying glass emoji
- Subtitle: "AI-Powered Hype Investigation Tool"
- Description: "Paste any tweet, GitHub repo, or project URL. Get an instant trust report backed by network analysis, code audits, and claim verification."

**Try it section:**
- Input field for URL(s) — textarea, one per line
- "Check Now" button
- Results area that shows:
  - Verdict badge (LEGIT green / SUSPICIOUS yellow / LIKELY_HYPE red)
  - Trust score as a big number with circular progress
  - Stage scores table
  - Evidence list
  - "Get Full Report" button (teaser for paid)

**How it works section:**
- 7 pipeline stages visualized as a flow
- Each stage: icon + name + one-line description

**Case Study section:**
- MiroFish investigation summary
- Show the 32/100 score, key findings
- "This is what HypeCheck caught in 30 seconds"

**Pricing section:**
- Free: 3 checks/day, basic verdict
- Pro ($49/mo): Unlimited checks, full reports, API access, JSON export
- Enterprise ($199/mo): Batch processing, webhooks, priority support

**Footer:**
- "Built by WiseChef" with link to wisechef.ai
- GitHub link for open-source CLI
- "Powered by OSINT, not opinions"

### Design:
- Dark theme (matches crypto/security vibe)
- Colors: dark bg (#0a0a0a), accent green (#22c55e) for LEGIT, yellow (#eab308) for SUSPICIOUS, red (#ef4444) for LIKELY_HYPE
- Font: Inter or system-ui
- No framework needed — vanilla HTML/CSS/JS
- Mobile responsive
- The form POSTs to /api/hypecheck/check via fetch()

### JavaScript behavior:
- On form submit: POST to /api/hypecheck/check with { urls: [...], full: false }
- Show loading spinner during check
- Render results with animated trust score counter
- Error handling for rate limits (show "Upgrade to Pro for unlimited checks")

## 3. Integration

The landing page will be served at wisechef.ai/hypecheck via the existing Express server.
The API will run as a separate process on port 3347, proxied at /api/hypecheck/*.

DO NOT modify server.js or any files outside this repo.
Just build the api/ and landing/ directories.

## 4. Run script

Create `run-api.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true
exec uvicorn api.main:app --host 0.0.0.0 --port 3347
```
