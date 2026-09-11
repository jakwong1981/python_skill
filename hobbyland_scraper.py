#!/usr/bin/env python3
"""
Hobbyland E-shop / animes-pro.com — Gunpla catalog scraper (HG / MG / RG / animes-pro HG)

The hobbylandeshop.com frontend is a Vue single-page app: opening a category page such as

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

For animes-pro.com (Shopify-based) the scraper uses the standard Shopify
/products.json endpoint instead:

    GET https://animes-pro.com/collections/{handle}/products.json?page={n}

Iteration continues until the products array is empty.

Each category is written to its own CSV:
  hg    -> hobbyland_hg.csv   (model_area > gundam_zone > hg_high_grade)
  mg    -> hobbyland_mg.csv   (model_area > gundam_zone > mg_master_grade)
  rg    -> hobbyland_rg.csv   (model_area > gundam_zone > rg_real_grade)
  ap_hg -> animes-pro_hg.csv  (animes-pro.com Shopify collection)

Usage:
  python3 hobbyland_scraper.py           # scrape all categories
  python3 hobbyland_scraper.py hg rg     # scrape selected categories only
  python3 hobbyland_scraper.py ap_hg     # scrape animes-pro HG only
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
ANIME_PRO_BASE_URL = "https://animes-pro.com"

# category key -> (output CSV, path segments under /product-category/)
CATEGORIES = {
    "hg": ("hobbyland_hg.csv",
           ["model_area", "gundam_zone", "hg_high_grade"]),
    "mg": ("hobbyland_mg.csv",
           ["model_area", "gundam_zone", "mg_master_grade"]),
    "rg": ("hobbyland_rg.csv",
           ["model_area", "gundam_zone", "rg_real_grade"]),
}

# animes-pro.com (Shopify) categories: key -> (output CSV, collection handle)
ANIME_PRO_CATEGORIES = {
    "ap_hg": ("animes-pro_hg.csv", "high-grade-hg%E6%A8%A1%E5%9E%8B"),
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


def _fetch_animes_pro_page(collection_handle, page):
    """GET /collections/{handle}/products.json?page={page}; returns product list."""
    url = (f"{ANIME_PRO_BASE_URL}/collections/{collection_handle}"
           f"/products.json?page={page}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("products", [])


def fetch_animes_pro_page_with_retry(collection_handle, page):
    """Fetch one animes-pro page, retrying transient failures."""
    for attempt in range(1, PAGE_ATTEMPTS + 1):
        try:
            return _fetch_animes_pro_page(collection_handle, page)
        except (urllib.error.URLError, TimeoutError,
                json.JSONDecodeError) as exc:
            if attempt == PAGE_ATTEMPTS:
                raise
            print(f"   ⚠️  Page {page} failed (attempt {attempt}/"
                  f"{PAGE_ATTEMPTS}): {exc}")
            time.sleep(RETRY_WAIT_S)
    return None  # unreachable


def scrape_animes_pro_category(collection_handle):
    """Scrape all pages from an animes-pro.com Shopify collection.

    Shopify's /products.json endpoint returns an empty array when there are
    no more pages, so we iterate until we hit an empty page.
    """
    products = []
    seen_urls = set()
    page = 1

    while True:
        batch = fetch_animes_pro_page_with_retry(collection_handle, page)
        if not batch:
            print(f"   — page {page}: empty, collection exhausted")
            break

        added = 0
        for item in batch:
            handle = item.get("handle", "")
            url = f"{ANIME_PRO_BASE_URL}/products/{handle}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            variants = item.get("variants", [])
            price = variants[0].get("price", "") if variants else ""
            products.append({
                "title": item.get("title", "").strip(),
                "price": price,
                "url": url,
                "regular_price": "",
                "sku": "",
                "stock": "",
                "sell_type": "",
            })
            added += 1

        print(f"   Page {page}: {len(batch)} items (+{added} new)")
        page += 1
        time.sleep(PAGE_WAIT_S)

        if page > 200:  # safety guard
            print("   ⚠️  Safety limit of 200 pages reached — stopping")
            break

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
    print("  HOBBYLAND / ANIMES-PRO — GUNPLA CATALOG SCRAPER")
    print("=" * 70 + "\n")

    # Merge both category dicts for CLI lookup
    all_cats = {**CATEGORIES, **ANIME_PRO_CATEGORIES}

    # Optional argv selects categories; default = all
    keys = [arg.lower() for arg in argv]
    unknown = [k for k in keys if k not in all_cats]
    if unknown:
        print(f"❌ Unknown category: {', '.join(unknown)}")
        print(f"   Available: {', '.join(all_cats)}")
        return 2
    if not keys:
        keys = list(all_cats)

    exit_code = 0
    for key in keys:
        label = key.upper()

        if key in ANIME_PRO_CATEGORIES:
            # --- animes-pro.com (Shopify) branch ---
            csv_name, handle = ANIME_PRO_CATEGORIES[key]
            print(f"🔗 [{label}] Collection: "
                  f"{ANIME_PRO_BASE_URL}/collections/{handle}\n")
            try:
                products = scrape_animes_pro_category(handle)
            except Exception as exc:
                print(f"\n❌ [{label}] Scraping failed: {exc}\n")
                exit_code = 1
                continue
        else:
            # --- Hobbyland (Vue SPA API) branch ---
            csv_name, segments = CATEGORIES[key]
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
