# Python Programs

A collection of standalone Python utilities for macOS.

## Programs

| File | Purpose | Usage | Output |
|------|---------|-------|--------|
| `consolidate_model_keys.py` | Scan macOS for AI-model / API keys across shell profiles, `.env` files, and AI agent config directories; identify the provider and consuming agent for each key; export a consolidated Excel spreadsheet. | `python3 consolidate_model_keys.py [--full] [--out PATH]` | `~/Desktop/model_keys_review.xlsx` (masked by default; `--full` for raw values, file set to `chmod 600`) |
| `parser_gmail_bill.py` | Search Gmail for credit-card transaction emails, extract card info, amounts (original / HKD), and receipt URLs; export to CSV. | `python3 parser_gmail_bill.py` | `bill.csv` (only written when at least one email contains an amount) |
| `pbandai_scraper_v2.py` | Scrape P-Bandai HK product listings using Playwright (real browser to bypass Cloudflare); translates product names to Traditional Chinese. | `python3 pbandai_scraper_v2.py` | `pbandai_products.csv` / `.json` / `.xlsx` (fixed names, include a `TC Product Name` field) |
| `hobbyland_scraper.py` | Scrape the Hobbyland E-shop Gunpla catalog (HG / MG / RG): reads the total page count per category from the shop's JSON API, loops every `?page=x`, and collects each item's title, price, and detail-page link. | `python3 hobbyland_scraper.py [hg] [mg] [rg]` (no args = all) | `hobbyland_hg.csv` / `hobbyland_mg.csv` / `hobbyland_rg.csv` (fixed names; stdlib only, no browser) |

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

1. **Loads** the P-Bandai shop page first (statically served, reliable), then tops up with the bot-protected category search page (gunpla, `_f_categories=04-004`) when it is reachable.
2. **Extracts** each product's name, price, status, and item URL via in-page JavaScript.
3. **Translates** each product name from English to Traditional Chinese into a `TC Product Name` field. Translation tries free online services (Google/MyMemory) first, then a local Helsinki-NLP model — free endpoints throttle bursts of requests, so the offline engine guarantees a result; the English name is kept only when every engine is unavailable.
4. **Exports** the results as fixed-name `pbandai_products.csv`, `.json`, and `.xlsx` files (overwritten on each run).

**Setup**: `pip3 install playwright deep-translator` then `python3 -m playwright install chromium`. For the guaranteed offline translation fallback also run `pip3 install torch transformers sentencepiece opencc-python-reimplemented` (downloads the ~310 MB Helsinki-NLP model on first use). The output files are git-ignored.

**Tunable constants** (top of the script): `SEARCH_ATTEMPTS` (search top-up tries after the shop page, default 1), `SEARCH_RETRY_WAIT_S` (pause between tries), and `HEADLESS` (set to `False` to watch the browser run).

### hobbyland_scraper.py

Scrapes the Hobbyland E-shop Gunpla categories — HG High Grade (`hg_high_grade`), MG Master Grade (`mg_master_grade`), and RG Real Grade (`rg_real_grade`), all under `model_area > gundam_zone`:

1. **Discovers the max page count** per category from page 1's response (`total_pages` — the same number as the last button in the pagination bar at the bottom of the category page).
2. **Loops every page** `1..max` by posting to the shop's JSON API (`POST backend.hobbylandeshop.com/api/products` with `{"page": x, "category": [...], "stockStatus": "in_stock"}`) — the site is a Vue SPA, so category URLs return only an empty HTML shell; the frontend itself maps `?page=x` to this API call.
3. **Extracts** each item's title (description), price and regular price, SKU, stock, availability (`sell_type`), and detail-page hyperlink.
4. **Exports** one isolated CSV per category (`hobbyland_hg.csv` / `hobbyland_mg.csv` / `hobbyland_rg.csv`, UTF-8 BOM, overwritten on each run), with the required `title`, `price`, `url` fields followed by the helper columns.

Run `python3 hobbyland_scraper.py` for all categories, or pass a subset, e.g. `python3 hobbyland_scraper.py hg rg`.

**Setup**: none — Python 3 standard library only, no browser or extra packages. The API is not bot-protected, so plain HTTPS requests suffice.

## Requirements

- **Python 3.7+** (standard library only for core functionality)
- **openpyxl** — required for Excel output (`pip install openpyxl`)
- **google-api-python-client**, **google-auth-oauthlib** — required for Gmail parsing (`pip install google-api-python-client google-auth-oauthlib`)
- **playwright** — required for P-Bandai scraping (`pip3 install playwright && python3 -m playwright install chromium`)
- **deep-translator** — free online translation backends (Google/MyMemory) for P-Bandai product names (`pip3 install deep-translator`)
- **transformers**, **torch**, **sentencepiece**, **opencc-python-reimplemented** *(optional but recommended)* — offline Helsinki-NLP translation fallback so names are translated even when the free online endpoints throttle requests (`pip3 install torch transformers sentencepiece opencc-python-reimplemented`; the model downloads once on first use)
- **PyYAML** *(optional)* — improves Hermes `config.yaml` parsing; falls back to regex if absent
