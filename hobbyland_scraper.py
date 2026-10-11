#!/usr/bin/env python3
"""
Hobbyland E-shop / animes-pro.com — Gunpla catalog scraper (HG / MG / RG)

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

For animes-pro.com (Shopify-based) the scraper walks the rendered HTML
listing instead:

    GET https://animes-pro.com/collections/{handle}?page={n}

Since Sep 2026 the shop sits behind Shopify bot protection: collection
pages answer 302 with a ``__shopify_bv_challenge`` URL and /products.json
hard-429s scripted clients, so plain urllib is no longer enough. A real
browser (Playwright/Chromium, same trick as pbandai_scraper_v2.py) solves
the JS challenge, then each listing page's product cards are parsed from
the DOM. A page with no cards means the collection is exhausted.

The kit identity
(`sku`) is the 13-digit JAN taken from the product name — the same column
Hobbyland fills from its API. animes-pro embeds that code in the title,
e.g. ``Y2700(4573102663849)``.

Each category is written to its own CSV:
  hg    -> hobbyland_hg.csv   (model_area > gundam_zone > hg_high_grade)
  mg    -> hobbyland_mg.csv   (model_area > gundam_zone > mg_master_grade)
  rg    -> hobbyland_rg.csv   (model_area > gundam_zone > rg_real_grade)
  ap_hg -> animes-pro_hg.csv  (animes-pro.com Shopify collection)
  ap_mg -> animes-pro_mg.csv
  ap_rg -> animes-pro_rg.csv

Usage:
  python3 hobbyland_scraper.py                 # scrape all categories
  python3 hobbyland_scraper.py hg rg           # scrape selected categories only
  python3 hobbyland_scraper.py ap_hg ap_mg ap_rg
"""

import csv
import json
import re
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
    "ap_mg": ("animes-pro_mg.csv", "master-grade-mg%E6%A8%A1%E5%9E%8B"),
    "ap_rg": ("animes-pro_rg.csv", "real-grade-rg%E6%A8%A1%E5%9E%8B"),
}

# 13-digit JAN in a product name, e.g. Y2700(4573102663849). Same identity
# column as hobbyland_*.csv `sku`.
JAN_RE = re.compile(r"(?<!\d)(4\d{12})(?!\d)")

STOCK_STATUS = "in_stock"   # matches the shop's default listing tab

# CSV columns: the three spec fields first, then helpful extras
FIELDNAMES = ["title", "price", "url",
              "regular_price", "sku", "stock", "sell_type", "image_url"]

# hobbyland 圖片 CDN：API 只回傳相對路徑（pic1），站台前綴見 frontend resource helper
STATIC_BASE_URL = "https://static.hobbylandeshop.com/"

# --- Request tuning ---
PAGE_ATTEMPTS = 6       # retries per page before giving up
RETRY_WAIT_S = 3        # pause between retries when the shop gives no wait
PAGE_WAIT_S = 1.5       # polite delay between page requests
MAX_RETRY_WAIT_S = 90   # cap a hostile Retry-After value

# --- animes-pro browser tuning (Shopify bot protection) ---
AP_HEADLESS = True          # set False to watch the challenge being solved
AP_CHALLENGE_WAIT_S = 45    # budget for the bv challenge to clear

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/152.0.0.0 Safari/537.36")


def jan_from_name(title):
    """13-digit JAN embedded in a product name, or '' if there is none."""
    match = JAN_RE.search(title or "")
    return match.group(1) if match else ""


def animes_pro_row(card):
    """One rendered listing card -> the same columns as a Hobbyland CSV row.

    `card` comes from the browser-side extraction in
    `_ANIME_PRO_CARD_JS` ({title, href, price, compare, img}). `sku` comes from
    the product name, matching hobbyland_*.csv.
    """
    title = (card.get("title") or "").strip()
    href = card.get("href") or ""
    handle = re.search(r"/products/([^?#]+)", href)
    if "【預訂" in title:
        sell_type = "預訂"
    elif "【現貨" in title:
        sell_type = "現貨"
    else:
        sell_type = ""
    return {
        "title": title,
        "price": card.get("price") or "",
        "url": (f"{ANIME_PRO_BASE_URL}/products/{handle.group(1)}"
                if handle else ANIME_PRO_BASE_URL + href),
        "regular_price": card.get("compare") or "",
        "sku": jan_from_name(title),
        "stock": "",
        "sell_type": sell_type,
        "image_url": card.get("img") or "",
    }


def _hobbyland_image_url(pic):
    """API 的 pic1 是相對路徑（storage/...），補上 static CDN 前綴。"""
    pic = (pic or "").strip()
    if not pic:
        return ""
    if pic.startswith(("http://", "https://")):
        return pic
    return STATIC_BASE_URL + pic.lstrip("/")


def _category_url(segments):
    return BASE_URL + "/product-category/" + "/".join(segments)


def retry_wait_seconds(exc, fallback=RETRY_WAIT_S):
    """Seconds to wait before the next attempt.

    Shopify answers HTTP 429 with ``Retry-After: 60``. Sleeping the old
    fixed 3 seconds burns the remaining attempts and the scrape dies.
    """
    headers = getattr(exc, "headers", None)
    raw = headers.get("Retry-After") if headers is not None else None
    try:
        wait = int(str(raw))
    except (TypeError, ValueError):
        wait = fallback
    return min(max(wait, 1), MAX_RETRY_WAIT_S)


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
    return _with_retry(lambda: _fetch_page(segments, page), f"Page {page}")


def _with_retry(fn, what):
    """Call fn(), waiting out HTTP 429 Retry-After between attempts."""
    for attempt in range(1, PAGE_ATTEMPTS + 1):
        try:
            return fn()
        except (urllib.error.URLError, TimeoutError,
                json.JSONDecodeError, RuntimeError) as exc:
            if attempt == PAGE_ATTEMPTS:
                raise
            wait = retry_wait_seconds(exc)
            print(f"   ⚠️  {what} failed (attempt {attempt}/"
                  f"{PAGE_ATTEMPTS}): {exc} — waiting {wait}s")
            time.sleep(wait)
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
                "image_url": _hobbyland_image_url(item.get("pic1", "")),
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


# Browser-side extraction of one listing page's product cards.
# Selectors match the shop's current Shopify theme (.product-block grid).
_ANIME_PRO_CARD_JS = """() => [...document.querySelectorAll('.product-block')].map(c => {
  const a = c.querySelector('.product-block__title-link');
  const money = sel => {
    const el = c.querySelector(sel);
    return el ? el.innerText.replace(/[^0-9.]/g, '') : '';
  };
  const img = c.querySelector('.product-block__image img, .product-block img');
  let imgSrc = '';
  if (img) {
    // Shopify lazy-load：未載入的圖 src 係 data: placeholder，真網址喺 data-src / srcset
    const srcset = (img.getAttribute('data-srcset') || img.getAttribute('srcset') || '')
      .split(',')[0].trim().split(' ')[0];
    const candidates = [img.currentSrc, img.src, img.getAttribute('data-src'), srcset];
    imgSrc = candidates.find(u => u && !u.startsWith('data:')) || '';
    if (imgSrc.startsWith('//')) imgSrc = 'https:' + imgSrc;
    // 部分主題用 {width} 模板位，換返個實際寬度先用得
    imgSrc = imgSrc.replace('{width}', '300');
  }
  return {
    title: a ? a.innerText.trim() : '',
    href: a ? a.getAttribute('href') : '',
    price: money('.product-price__reduced')
        || money('.product-price__regular')
        || money('.theme-money'),
    compare: money('.product-price__compare'),
    img: imgSrc,
  };
})"""


def _solve_animes_pro_challenge(page, collection_handle):
    """Open the collection page and wait out Shopify's bv challenge.

    The challenge page auto-submits its JS proof and reloads the real
    listing, so success = product cards appear within the wait budget.
    """
    url = f"{ANIME_PRO_BASE_URL}/collections/{collection_handle}"
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    if not _wait_animes_pro_listing(page):
        raise RuntimeError(
            f"Shopify bot challenge did not clear for {url} "
            f"(now at {page.url}) — set AP_HEADLESS = False to watch")


def _wait_animes_pro_listing(page, timeout_s=AP_CHALLENGE_WAIT_S):
    """True once listing cards render; False on timeout (challenge/empty)."""
    try:
        page.wait_for_selector(".product-block", timeout=timeout_s * 1000)
        return True
    except Exception:
        return False


def scrape_animes_pro_category(collection_handle):
    """Scrape all pages from an animes-pro.com Shopify collection.

    The shop is behind Shopify bot protection and /products.json is
    rate-limited to death for scripted clients, so a real browser solves
    the JS challenge and then walks the rendered HTML listing pages
    (?page=N) — exactly what a human visitor sees. A page with no cards
    means the collection is exhausted.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "animes-pro.com requires a real browser (Shopify bot "
            "protection) — install Playwright: pip install playwright && "
            "python3 -m playwright install chromium") from exc

    products = []
    seen_urls = set()
    base = f"{ANIME_PRO_BASE_URL}/collections/{collection_handle}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=AP_HEADLESS)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK",
        )
        page = context.new_page()
        _solve_animes_pro_challenge(page, collection_handle)

        page_num = 1
        while True:
            if page_num > 1:
                page.goto(f"{base}?page={page_num}",
                          wait_until="domcontentloaded", timeout=30000)
                if not _wait_animes_pro_listing(page, timeout_s=15):
                    # past the last page Shopify renders an empty grid
                    print(f"   — page {page_num}: no cards, "
                          "collection exhausted")
                    break

            batch = page.evaluate(_ANIME_PRO_CARD_JS)
            if not batch:
                print(f"   — page {page_num}: empty, collection exhausted")
                break

            added = 0
            for card in batch:
                row = animes_pro_row(card)
                if not row["url"] or row["url"] in seen_urls:
                    continue
                seen_urls.add(row["url"])
                products.append(row)
                added += 1

            print(f"   Page {page_num}: {len(batch)} items (+{added} new)")
            if added == 0:
                print("   ⚠️  No new items — pagination wrapped, stopping")
                break

            page_num += 1
            time.sleep(PAGE_WAIT_S)

            if page_num > 200:  # safety guard
                print("   ⚠️  Safety limit of 200 pages reached — stopping")
                break

        browser.close()

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
