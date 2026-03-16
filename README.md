# HypeCheck

HypeCheck is an open-source CLI that investigates hyped AI/crypto projects on social media and produces trust reports.

## Features

- 7-stage investigation pipeline:
  - intake
  - scrape
  - network
  - code_audit
  - verify_claims
  - timeline
  - report
- X scraping via syndication API + fxtwitter for individual posts
- GitHub repository analysis via public REST API (optional `GITHUB_TOKEN` support)
- Polymarket wallet/profile checks via public Gamma/Data APIs
- Optional OpenAI-compatible LLM synthesis (`OPENAI_API_KEY`)
- Works without LLM for baseline analysis

## Installation

```bash
pip install -e .
```

## Usage

```bash
hypecheck <url>
hypecheck <url> --full
hypecheck <url> --json
hypecheck report <report-id>
```

Examples:

```bash
hypecheck https://x.com/zostaff/status/2033209676918145231
hypecheck https://github.com/openai/openai-python --json
hypecheck report 20260316T153000Z_abc1234567.json
```

Reports are saved to `.hypecheck/reports/` by default.

## Environment Variables

```bash
OPENAI_API_KEY=
OPENAI_BASE_URL=
OPENAI_MODEL=gpt-4o-mini
GITHUB_TOKEN=
HYPECHECK_TIMEOUT=20
HYPECHECK_REPORT_DIR=.hypecheck/reports
```

## Notes

- X post scraping uses:
  - `https://api.fxtwitter.com/status/{tweet_id}`
  - `https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}`
- GitHub scraping uses `https://api.github.com`
- Polymarket uses:
  - `https://gamma-api.polymarket.com/`
  - `https://data-api.polymarket.com/`

## License

MIT
