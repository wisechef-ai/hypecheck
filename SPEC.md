# HypeCheck — AI Hype Verification Tool

## Overview
Open-source CLI + API that investigates hyped AI/crypto projects and produces trust reports. Takes a URL (X post, GitHub repo, or website) and runs an automated investigation pipeline.

## Architecture

### CLI Interface
```bash
hypecheck <url>                    # Quick check
hypecheck <url> --full             # Full investigation
hypecheck <url> --json             # Machine-readable output
hypecheck report <report-id>       # View saved report
```

### Core Pipeline (7 stages)

1. **Intake** (`src/stages/intake.py`)
   - Parse input URL, classify type: x_post | github_repo | website | polymarket_wallet
   - Extract metadata (author, repo owner, domain)
   - If X post: follow quote chain to find all related posts

2. **Scrape** (`src/stages/scrape.py`)
   - X posts: use nitter instances or syndication API to get content, likes, retweets, timestamps, quoted posts
   - GitHub repos: use GitHub API to get README, package files, .env.example, star count, contributor info
   - Websites: basic web fetch for landing page content

3. **Network Map** (`src/stages/network.py`)
   - Given a set of X accounts from the quote chain:
     - Check bios for shared group affiliations (like @zscdao)
     - Check posting patterns (timestamps clustering)
     - Check if accounts cross-reference each other
     - Score: coordination_likelihood (0-100)

4. **Code Audit** (`src/stages/code_audit.py`)
   - If GitHub repo provided:
     - Scan package.json, pyproject.toml, requirements.txt for:
       - Crypto/wallet libraries (ethers, web3, wagmi, etc.)
       - Known malicious packages
       - Suspicious postinstall scripts
     - Scan .env.example for wallet-related vars (PRIVATE_KEY, SEED_PHRASE, etc.)
     - Check if claimed functionality (e.g., "Polymarket trading") matches actual code
     - Score: security_risk (low | medium | high | critical)

5. **Claim Verification** (`src/stages/verify_claims.py`)
   - Extract profit claims from scraped posts (regex for $XXX patterns)
   - If Polymarket wallet addresses found:
     - Query Polymarket Data API for actual positions, PnL
     - Compare claimed vs actual numbers
   - If specific accounts/usernames cited:
     - Look up public profiles
   - Score: claims_verified (0-100, with specific discrepancies listed)

6. **Timeline Analysis** (`src/stages/timeline.py`)
   - Plot all related posts on a timeline
   - Detect patterns: seed post → amplification → hype layer
   - Check for suspicious clustering (many posts within 24-48h)
   - Identify the "patient zero" post
   - Score: coordination_score (0-100)

7. **Report Generation** (`src/stages/report.py`)
   - Synthesize all stage outputs into a trust report
   - Overall trust score (0-100)
   - Traffic light verdict: ✅ LEGIT | ⚠️ SUSPICIOUS | 🚨 LIKELY HYPE
   - Key findings with evidence
   - LLM summary (gpt-4o-mini) connecting the dots

### Project Structure
```
hypecheck/
├── src/
│   ├── __init__.py
│   ├── cli.py              # Click CLI interface
│   ├── pipeline.py          # Orchestrates all stages
│   ├── config.py            # API keys, settings
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── intake.py
│   │   ├── scrape.py
│   │   ├── network.py
│   │   ├── code_audit.py
│   │   ├── verify_claims.py
│   │   ├── timeline.py
│   │   └── report.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── x_scraper.py     # X/Twitter scraping via syndication
│   │   ├── github_scraper.py # GitHub API
│   │   └── polymarket.py    # Polymarket Data API
│   └── utils/
│       ├── __init__.py
│       ├── llm.py           # OpenAI-compatible LLM client
│       └── scoring.py       # Trust score computation
├── tests/
│   └── test_pipeline.py
├── pyproject.toml
├── README.md
├── LICENSE                  # MIT
└── .env.example
```

### Dependencies
- click (CLI)
- httpx (async HTTP)
- beautifulsoup4 (HTML parsing)  
- openai (LLM synthesis, optional — works without for basic checks)
- rich (terminal output formatting)

### Environment Variables
```
# Optional - enables LLM report synthesis
OPENAI_API_KEY=sk-...

# Optional - higher GitHub API rate limits
GITHUB_TOKEN=ghp_...
```

### Trust Score Formula
```
trust_score = (
    code_safety_weight * code_audit_score +        # 30%
    claims_weight * claims_verification_score +     # 30%
    network_weight * (100 - coordination_score) +   # 20%
    timeline_weight * (100 - clustering_score)      # 20%
)
```

### Output Format (JSON)
```json
{
  "url": "https://x.com/...",
  "verdict": "LIKELY_HYPE",
  "trust_score": 23,
  "summary": "MiroFish is a legitimate simulation tool, but profit claims...",
  "stages": {
    "code_audit": { "risk": "low", "findings": [...] },
    "claims": { "score": 15, "discrepancies": [...] },
    "network": { "coordination": 82, "shared_groups": ["@zscdao"] },
    "timeline": { "clustering": 91, "seed_post": "...", "amplification_window_hours": 120 }
  },
  "evidence": [...],
  "generated_at": "2026-03-16T15:30:00Z"
}
```

## Key Design Decisions
- **No browser automation for MVP** — use syndication API / nitter for X, GitHub REST API, Polymarket REST API. Keeps it fast and reliable.
- **LLM is optional** — basic checks (code audit, timeline) work without any API key. LLM only needed for report synthesis.
- **CLI-first** — no web frontend in MVP. Web/API comes later as the paid tier.
- **MIT license** — maximum adoption.
- **Python** — matches our existing tooling (scrapling, cognee, etc.)

## Test Case
The MiroFish investigation we already did is the test case. The tool should reproduce our findings:
- Code audit: low risk, no wallet/trading code
- Claims: unverified, wallet numbers don't match
- Network: high coordination (zscdao connection)
- Timeline: clear seed → amplification pattern
- Verdict: LIKELY_HYPE, trust_score ~20-25
