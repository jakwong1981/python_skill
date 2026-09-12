# AGENTS.md

Standalone Python 3 utility scripts for macOS — no package, no shared library.
Each file is an independent script run directly with `python3 <file>.py`: Gunpla
catalogue scrapers (Hobbyland, animes-pro, P-Bandai HK), a Gmail credit-card
bill parser, and an API-key consolidator. There is no build system, linter, CI,
or dependency manifest — nothing to install or compile for the repo as a whole.

## Layout

- `hobbyland_scraper.py` — Gunpla catalogue scraper (Hobbyland Vue API + animes-pro Shopify), stdlib only
- `pbandai_scraper_v2.py` — P-Bandai HK scraper (Playwright/Chromium to bypass Cloudflare)
- `parser_gmail_bill.py` — Gmail credit-card transaction parser → `bill.csv`
- `consolidate_model_keys.py` — scan `$HOME` for AI API keys → Excel
- `test_*.py` — unittest suites (see Tests); `*.sh` are one-shot setup/launch scripts
- `venv/` — local Python 3.14 virtualenv (self-ignored); CSV/JSON/XLSX outputs are generated and git-ignored

## Dev environment

- Activate the project venv: `source venv/bin/activate` (Python 3.14.7). System
  `pip` points at Python 3.9 while `python3` is 3.14; system site-packages are
  externally managed (PEP 668), so install deps into the venv, not system Python.
- No `requirements.txt` / `pyproject.toml`. Dependencies are per-script and
  documented in each file's docstring + README:
  - `pip install openpyxl` — `consolidate_model_keys.py` (Excel output)
  - `pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client` — `parser_gmail_bill.py`
  - `pip install playwright deep-translator && python3 -m playwright install chromium` — `pbandai_scraper_v2.py`
  - `pip install torch transformers sentencepiece opencc-python-reimplemented` — optional offline translation fallback for `pbandai_scraper_v2.py` (~310 MB model on first run)
  - `pip install PyYAML` — optional, better Hermes `config.yaml` parsing in `consolidate_model_keys.py`
- `hobbyland_scraper.py` needs nothing beyond the stdlib.

## Running the scripts

All scripts use relative paths for their inputs/outputs — run them from the repo root.

| Script | Command | Output |
|---|---|---|
| Hobbyland | `python3 hobbyland_scraper.py` or `python3 hobbyland_scraper.py hg rg ap_hg` | `hobbyland_hg.csv` / `_mg.csv` / `_rg.csv`, `animes-pro_hg.csv` |
| P-Bandai | `python3 pbandai_scraper_v2.py` | `pbandai_products.csv` / `.json` / `.xlsx` |
| Gmail bill | `python3 parser_gmail_bill.py` | `bill.csv` (only if ≥1 email has an amount) |
| Key scan | `python3 consolidate_model_keys.py [--full] [--out PATH]` | Excel (values masked by default) |

## Tests

unittest-based; no pytest config required. Both run as plain scripts:

```
python3 test_pbandai_outputs.py -v
python3 test_hobbyland_digest.py -v
# or, if pytest is installed:  pytest
```

- `test_pbandai_outputs.py` validates the generated `pbandai_products.*` files —
  run `pbandai_scraper_v2.py` first or it fails on missing files. The xlsx test
  skips if `openpyxl` is absent.
- `test_hobbyland_digest.py` imports `~/.hermes/scripts/hobbyland_hourly.py` by
  absolute path (lives OUTSIDE this repo) — it raises ImportError if that file
  is not present.
- `test_translater.py` is a live smoke test of `deep-translator` (exits 1 if
  missing), not a unittest.

## Conventions

- Each script is self-contained: a module docstring with a `Usage:` block,
  tunable UPPER_SNAKE constants at the top (URLs, retry counts, worker counts),
  and a `main()` guarded by `if __name__ == "__main__"`.
- CSVs are written UTF-8 with a BOM (`encoding="utf-8-sig"`).
- Output files use fixed names and are overwritten each run; a scraper/parser
  writes nothing when it finds no data.
- Comments and docstrings freely mix English and Traditional Chinese — keep that
  flavour rather than translating existing text.
- Commit messages are short imperative summaries, occasionally `feat(scope):`
  prefixed (e.g. `feat(scraper): add Playwright-based P-Bandai HK product scraper`).

## Pitfalls

- `.gitignore` ignores `*.json` and `*.csv` globally, but NOT `__pycache__/` or
  `*.pyc` — compiled files show up as untracked in `git status`.
- `credentials.json` and `token.json` (Gmail OAuth) are secrets — never commit.
  First run of `parser_gmail_bill.py` opens a browser for OAuth consent.
- The P-Bandai search endpoint is Cloudflare-protected and intermittently
  returns "PAGE NOT AVAILABLE"; retry/timeout budgets are bounded via the
  `SEARCH_*` / `PAGE_LOAD_ATTEMPTS` constants. Set `HEADLESS = False` to watch.
- Scrapers hit live third-party sites and are slow (P-Bandai paginates up to
  `MAX_PAGES` with per-page waits).
