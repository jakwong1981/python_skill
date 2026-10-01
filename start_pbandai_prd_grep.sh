#!/bin/bash
# Launch the P-Bandai HK scraper using the project venv (system python3 is
# PEP 668 externally-managed, so deps must live in venv/, not --user).
set -e
cd "$(dirname "$0")"

PY=venv/bin/python
if [ ! -x "$PY" ]; then
  echo "venv not found — create it with: python3 -m venv venv" >&2
  exit 1
fi

# Required: Playwright (browser driver) + deep-translator (online translation)
"$PY" -m pip install --quiet playwright deep-translator
"$PY" -m playwright install chromium

# Optional: offline translation fallback (~310 MB model on first run).
# Uncomment to guarantee translations when the free online backends throttle.
# "$PY" -m pip install --quiet torch transformers sentencepiece opencc-python-reimplemented

"$PY" pbandai_scraper_v2.py
