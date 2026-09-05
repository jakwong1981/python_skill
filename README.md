# Python Programs

A collection of standalone Python utilities for macOS.

## Programs

| File | Purpose | Usage | Output |
|------|---------|-------|--------|
| `consolidate_model_keys.py` | Scan macOS for AI-model / API keys across shell profiles, `.env` files, and AI agent config directories; identify the provider and consuming agent for each key; export a consolidated Excel spreadsheet. | `python3 consolidate_model_keys.py [--full] [--out PATH]` | `~/Desktop/model_keys_review.xlsx` (masked by default; `--full` for raw values, file set to `chmod 600`) |
| `parser_gmail_bill.py` | Search Gmail for credit-card transaction emails, extract card info, amounts (original / HKD), and receipt URLs; export to CSV. | `python3 parser_gmail_bill.py` | `bill.csv` (only written when at least one email contains an amount) |
| `pbandai_scraper_v2.py` | Scrape P-Bandai HK product listings using Playwright (real browser to bypass Cloudflare). | `python3 pbandai_scraper_v2.py` | `pbandai_products_<timestamp>.json` / `.csv` / `.xlsx` |

## Details

### consolidate_model_keys.py

As developers increasingly work with multiple AI providers (OpenAI, Anthropic, Google Gemini, DeepSeek, etc.) and AI coding agents (Claude Code, Cursor, Codex, Hermes, Cline, etc.), API keys end up scattered across shell profiles, environment files, agent config directories, and JSON credential stores. This tool solves the "where did I put that key?" problem by:

1. **Scanning** ~20 well-known locations under `$HOME` for anything that looks like an API key, token, or secret.
2. **Identifying the provider** (30+ supported) based on the variable name and value pattern.
3. **Attributing each key to an agent/application** by cross-referencing installed AI coding agents, config-file references, and provider-prefix heuristics.
4. **Exporting a formatted Excel file** with key name, provider, consuming agent, source file, line number, and value — all in one place.

**Scanned locations** include: `.zshrc`, `.bashrc`, `.env`, `.hermes/`, `.claude/`, `.codex/`, `.cursor/`, `.cline/`, `.continue/`, `.openclaw/`, `.qoder/`, `.aws/credentials`, `.netrc`, and more.

**Detected agents**: Claude Code, Codex, Hermes Agent, Gemini CLI, Cursor, Windsurf, Cline, Continue, OpenCode, OpenClaw, Qoder, and others.

### parser_gmail_bill.py

Parses Gmail for credit-card transaction emails and exports a consolidated bill CSV:

1. **Searches** the inbox (last 30 days by default) for emails matching credit/card/payment/invoice/receipt/transaction keywords (English and Chinese).
2. **Filters** emails by card identifiers (Visa / Mastercard / 末四碼 last-4-digits, etc.), ignores job-platform mail such as JobsDB's "job db record", and skips emails with no amount found.
3. **Extracts** date, merchant, subject, original and HKD amounts, payment method, and receipt URL.
4. **Exports** `bill.csv` — the file is not written when no matching transactions are found.

**Setup**: requires `credentials.json` (OAuth client from Google Cloud Console) and `token.json` (generated on first run); both are git-ignored. On first execution a browser opens for Gmail authorization.

### pbandai_scraper_v2.py

Scrapes product listings from P-Bandai HK (Gunpla / assembly-model category by default) using Playwright to render the page in a real Chromium browser, avoiding Cloudflare blocks:

1. **Loads** the P-Bandai search page in headless Chromium and waits for product cards to appear.
2. **Extracts** each product's name, price, status, and item URL via in-page JavaScript.
3. **Exports** the results as timestamped JSON, CSV, and formatted Excel files.

**Setup**: `pip3 install playwright` then `python3 -m playwright install chromium`. The output files are git-ignored.

## Requirements

- **Python 3.7+** (standard library only for core functionality)
- **openpyxl** — required for Excel output (`pip install openpyxl`)
- **google-api-python-client**, **google-auth-oauthlib** — required for Gmail parsing (`pip install google-api-python-client google-auth-oauthlib`)
- **playwright** — required for P-Bandai scraping (`pip3 install playwright && python3 -m playwright install chromium`)
- **PyYAML** *(optional)* — improves Hermes `config.yaml` parsing; falls back to regex if absent
