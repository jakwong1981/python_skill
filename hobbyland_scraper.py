#!/usr/bin/env python3
"""
Hobbyland E-shop — Gunpla catalog scraper (HG / MG / RG)

The shop frontend is a Vue single-page app: opening a category page such as

    https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/hg_high_grade?page=2

returns only an empty HTML shell, and the browser then POSTs the page number
to the shop's JSON API

    POST https://backend.hobbylandeshop.com/api/products
    {"page": 2, "category": ["model_area", "gundam_zone", "hg_high_grade"],
     "stockStatus": "in_stock"}

This scraper uses that same endpoint instead of a browser. For every
category:
  1. page 1 is fetched and `total_pages` is read — the same number as the
     last button in the pagination bar at the bottom of the landing page;
  2. pages 1..total_pages are then looped, mirroring `?page=x`;
  3. every item's title (description), price, and detail-page hyperlink
     (plus SKU / stock / availability) is collected.

Each category is written to its own CSV:
  hg -> hobbyland_hg.csv   (model_area > gundam_zone > hg_high_grade)
  mg -> hobbyland_mg.csv   (model_area > gundam_zone > mg_master_grade)
  rg -> hobbyland_rg.csv   (model_area > gundam_zone > rg_real_grade)

Usage:
  python3 hobbyland_scraper.py           # scrape all categories
  python3 hobbyland_scraper.py hg rg     # scrape selected categories only
"""

import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# --- Site URLs ---
BASE_URL = "https://www.hobbylandeshop.com"
API_URL = "https://backend.hobbylandeshop.com/api/products"

# category key -> (output CSV, path segments under /product-category/)
CATEGORIES = {
    "hg": ("hobbyland_hg.csv",
           ["model_area", "gundam_zone", "hg_high_grade"]),
    "mg": ("hobbyland_mg.csv",
           ["model_area", "gundam_zone", "mg_master_grade"]),
    "rg": ("hobbyland_rg.csv",
           ["model_area", "gundam_zone", "rg_real_grade"]),
}

STOCK_STATUS = "in_stock"   # matches the shop's default listing tab

# CSV columns: the three spec fields first, then helpful extras
FIELDNAMES = ["title", "price", "url",
              "regular_price", "sku", "stock", "sell_type"]

# --- Request tuning ---
PAGE_ATTEMPTS = 3       # retries per page before giving up
RETRY_WAIT_S = 3        # pause between retries
PAGE_WAIT_S = 1.0       # polite delay between page requests

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/152.0.0.0 Safari/537.36")


def _category_url(segments):
    return BASE_URL + "/product-category/" + "/".join(segments)


def _fetch_page(segments, page):
    """POST /api/products for `page`; returns the parsed `data` dict."""
    body = json.dumps({
        "page": page,
        "category": segments,
        "stockStatus": STOCK_STATUS,
    }).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": BASE_URL + "/",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != 0:
        raise RuntimeError(f"API error code {payload.get('code')}: "
                           f"{payload.get('message')}")
    return payload["data"]


def fetch_page_with_retry(segments, page):
    """Fetch one page, retrying transient network/API failures."""
    for attempt in range(1, PAGE_ATTEMPTS + 1):
        try:
            return _fetch_page(segments, page)
        except (urllib.error.URLError, TimeoutError,
                json.JSONDecodeError, RuntimeError) as exc:
            if attempt == PAGE_ATTEMPTS:
                raise
            print(f"   ⚠️  Page {page} failed (attempt {attempt}/"
                  f"{PAGE_ATTEMPTS}): {exc}")
            time.sleep(RETRY_WAIT_S)
    return None  # unreachable


def scrape_category(segments, max_pages=None):
    """Loop pages 1..max for one category and return one dict per product.

    `max_pages` defaults to the shop's own page count (`total_pages`,
    reported by page 1 — the last number of the bottom pagination bar).
    """
    # Page 1 discovers the total / max page count
    data = fetch_page_with_retry(segments, 1)
    total = data.get("total")
    total_pages = data.get("total_pages")
    if max_pages is None:
        max_pages = total_pages
    print(f"📄 Page 1: {len(data.get('list', []))} items "
          f"({total} total, {total_pages} pages)")

    products = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        if page > 1:
            data = fetch_page_with_retry(segments, page)
            time.sleep(PAGE_WAIT_S)
        batch = data.get("list", [])
        added = 0
        for item in batch:
            url = BASE_URL + item.get("link", "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            products.append({
                "title": item.get("title", "").strip(),
                "price": item.get("price", ""),
                "url": url,
                "regular_price": item.get("regular_price", ""),
                "sku": item.get("sku", ""),
                "stock": item.get("stock", ""),
                "sell_type": item.get("sell_type", ""),
            })
            added += 1
        print(f"   Page {page}/{max_pages}: {len(batch)} items "
              f"(+{added} new)")
        if not batch:
            print("   ⚠️  Empty page — listing exhausted early")
            break
        if len(batch) < 28:
            print("   — final page reached")

    return products


def save_csv(products, filename):
    """Save one category to CSV (fixed filename, overwritten on each run)."""
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(products)
    return filename


def main(argv):
    print("=" * 70)
    print("  HOBBYLAND E-SHOP — GUNPLA CATALOG SCRAPER (HG / MG / RG)")
    print("=" * 70 + "\n")

    # Optional argv selects categories; default = all
    keys = [arg.lower() for arg in argv]
    unknown = [k for k in keys if k not in CATEGORIES]
    if unknown:
        print(f"❌ Unknown category: {', '.join(unknown)}")
        print(f"   Available: {', '.join(CATEGORIES)}")
        return 2
    if not keys:
        keys = list(CATEGORIES)

    exit_code = 0
    for key in keys:
        csv_name, segments = CATEGORIES[key]
        label = key.upper()
        print(f"🔗 [{label}] Category: {_category_url(segments)}\n")
        try:
            products = scrape_category(segments)
        except Exception as exc:
            print(f"\n❌ [{label}] Scraping failed: {exc}\n")
            exit_code = 1
            continue

        if not products:
            print(f"❌ [{label}] No products found — CSV not written.\n")
            exit_code = 1
            continue

        save_csv(products, csv_name)
        print(f"\n✅ [{label}] Saved {len(products)} products → {csv_name}\n")

        for p in products[:3]:
            print(f"  • {p['title'][:66]}")
            print(f"    💰 HK${p['price']}   🔗 {p['url'][:70]}")
        if len(products) > 3:
            print(f"\n  ... and {len(products) - 3} more")
        print()

    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
