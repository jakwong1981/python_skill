#!/usr/bin/env python3
"""
P-Bandai Web Scraper v2 - Uses Playwright (real browser) to bypass Cloudflare
Scrapes product information from P-Bandai HK

Installation:
  pip3 install playwright
  python3 -m playwright install chromium

Usage:
  python3 pbandai_scraper_v2.py
"""

import json
import csv
import os
import re
from datetime import datetime

def scrape_pbandai(url="https://p-bandai.com/hk/search?_f_categories=04-004"):
    """Scrape products using Playwright (real browser = no Cloudflare issues)"""
    from playwright.sync_api import sync_playwright
    
    products = []
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="zh-HK"
        )
        page = context.new_page()
        
        print(f"🔗 Opening: {url}\n")
        page.goto(url, wait_until="networkidle")
        
        # Wait for products to load
        page.wait_for_selector('a[href*="/hk/item/"]', timeout=15000)
        print("✓ Page loaded successfully\n")
        
        # Try to show 40 items per page
        try:
            show_40 = page.locator('button:has-text("40")')
            if show_40.is_visible():
                show_40.click()
                page.wait_for_timeout(2000)
                print("📄 Showing 40 items per page\n")
        except:
            pass
        
        # Extract product data via JavaScript
        result = page.evaluate("""() => {
            const products = [];
            const items = document.querySelectorAll('a[href*="/hk/item/"]');
            const seen = new Set();
            items.forEach(a => {
                const url = a.href;
                if (seen.has(url)) return;
                seen.add(url);
                const name = a.querySelector('p')?.innerText?.trim() || '';
                const allParas = a.querySelectorAll('p');
                const price = allParas.length > 1 ? allParas[1]?.innerText?.trim() : 'N/A';
                const statusEl = a.querySelector('li')?.innerText || '';
                if (name) {
                    products.push({ name, price, url, status: statusEl });
                }
            });
            return JSON.stringify(products);
        }""")
        
        browser.close()
        
        products = json.loads(result)
        print(f"📦 Found {len(products)} products\n")
        return products

def save_json(products, output_dir=None):
    """Save to JSON file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"pbandai_products_{timestamp}.json")
    else:
        filename = f"pbandai_products_{timestamp}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(products, f, ensure_ascii=False, indent=2)
    
    return filename

def save_csv(products, output_dir=None):
    """Save to CSV file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"pbandai_products_{timestamp}.csv")
    else:
        filename = f"pbandai_products_{timestamp}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'price', 'status', 'url'])
        writer.writeheader()
        writer.writerows(products)
    
    return filename

def save_xlsx(products, output_dir=None):
    """Save to Excel file (requires openpyxl)"""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
    except ImportError:
        print("⚠️  openpyxl not installed. Run: pip3 install openpyxl")
        return None
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        filename = os.path.join(output_dir, f"pbandai_products_{timestamp}.xlsx")
    else:
        filename = f"pbandai_products_{timestamp}.xlsx"
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'P-Bandai Products'
    
    # Headers
    headers = ['#', 'Product Name', 'Price (HKD)', 'Status', 'URL']
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2F5496', end_color='2F5496', fill_type='solid')
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Data
    for i, p in enumerate(products, 1):
        ws.cell(row=i+1, column=1, value=i)
        ws.cell(row=i+1, column=2, value=p['name'])
        price_clean = p['price'].replace('HK$‌', '').replace(',', '').strip()
        ws.cell(row=i+1, column=3, value=float(price_clean) if price_clean.replace('.','').isdigit() else price_clean)
        ws.cell(row=i+1, column=4, value=p['status'])
        cell = ws.cell(row=i+1, column=5, value=p['url'])
        cell.font = Font(color='0563C1', underline='single')
    
    # Column widths
    ws.column_dimensions['A'].width = 5
    ws.column_dimensions['B'].width = 75
    ws.column_dimensions['C'].width = 14
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 60
    
    wb.save(filename)
    return filename

def main():
    print("=" * 70)
    print("  P-BANDAI HK PRODUCT SCRAPER v2 (Playwright)")
    print("=" * 70 + "\n")
    
    # URL - Gunpla / 組裝模型 category
    url = "https://p-bandai.com/hk/search?_f_categories=04-004"
    
    # Scrape
    products = scrape_pbandai(url)
    
    if products:
        # Save files
        json_file = save_json(products)
        csv_file = save_csv(products)
        xlsx_file = save_xlsx(products)
        
        print(f"\n✅ Files saved:")
        print(f"   📄 JSON: {json_file}")
        print(f"   📄 CSV:  {csv_file}")
        if xlsx_file:
            print(f"   📊 XLSX: {xlsx_file}")
        
        # Print summary
        print(f"\n{'='*70}")
        print(f"📊 TOTAL: {len(products)} products")
        print(f"{'='*70}\n")
        
        for i, p in enumerate(products[:5], 1):
            print(f"  {i}. {p['name'][:65]}")
            print(f"     💰 {p['price']}")
        
        if len(products) > 5:
            print(f"\n  ... and {len(products)-5} more")
    else:
        print("\n❌ No products found.")
        print("   Check the URL or site accessibility.\n")

if __name__ == "__main__":
    main()
