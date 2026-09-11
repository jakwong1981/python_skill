# Web Scraping Specification: Hobbyland Gunpla Catalog

## Overview
Develop a Python-based web scraper to extract product listings across specific Gundam model kit categories from [Hobbyland E-Shop](https://www.hobbylandeshop.com/). The scraper must dynamically identify total page counts, paginate through product listings, parse product attributes, and export the structured data into dedicated CSV files.

---

## Target Data Fields
For each listed product, extract the following attributes:
* **Product Description / Title:** Full name or description of the kit.
* **Price:** Current listed retail price.
* **Product URL:** Direct hyperlink to the item's detail page.

---

## Scope & Target Categories

### 1. High Grade (HG)
* **Base URL:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/hg_high_grade`
* **Pagination Scheme:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/hg_high_grade?page={page_number}`
* **Output Destination:** `hobbyland_hg.csv`
### 1.1 High Grade animes-pro (HG)
 * **Base URL:** `https://animes-pro.com/collections/high-grade-hg%E6%A8%A1%E5%9E%8B`
 * **API Endpoint:** `https://animes-pro.com/collections/high-grade-hg%E6%A8%A1%E5%9E%8B/products.json`
 * **Pagination:** iterate `?page=1,2,...` until the array is empty (Shopify JSON)
 * **Output Destination:** `animes-pro_hg.csv`

### 2. Master Grade (MG)
* **Base URL:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/mg_master_grade`
* **Pagination Scheme:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/mg_master_grade?page={page_number}`
* **Output Destination:** `hobbyland_mg.csv`

### 3. Real Grade (RG)
* **Base URL:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/rg_real_grade`
* **Pagination Scheme:** `https://www.hobbylandeshop.com/product-category/model_area/gundam_zone/rg_real_grade?page={page_number}`
* **Output Destination:** `hobbyland_rg.csv`

---

## Technical Requirements & Workflow

1. **Pagination Detection:**
   * Fetch the landing page for each category.
   * Parse the pagination controls at the bottom of the page to determine the maximum page index ($N$).
2. **Data Extraction & Traversal:**
   * Iterate sequentially from `page=1` through `page=N`.
   * Parse each product card to retrieve the required fields (title/description, price, detail page link).
3. **Data Export:**
   * Write records to standard CSV format with appropriate headers (`title`, `price`, `url`).
   * Generate an isolated CSV file per product category as specified.
