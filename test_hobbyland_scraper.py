#!/usr/bin/env python3
"""Unit tests for hobbyland_scraper pure helpers. No network."""

import unittest
import urllib.error

import hobbyland_scraper as scraper

AP_TITLE = "Bandai - HG 1/144 機動戰士高達 突擊自由高達極  Y2700(4573102663849)【現貨】"
JAN = "4573102663849"


class TestJanFromName(unittest.TestCase):
    def test_jan_extracted_from_product_name(self):
        self.assertEqual(scraper.jan_from_name(AP_TITLE), JAN)

    def test_missing_jan_is_blank(self):
        self.assertEqual(scraper.jan_from_name("HG 1/144 2026"), "")

    def test_does_not_grab_a_shorter_number(self):
        self.assertEqual(scraper.jan_from_name("code 457310266384"), "")


class TestRetryAfter(unittest.TestCase):
    def test_honors_shopify_retry_after(self):
        exc = urllib.error.HTTPError(
            "https://animes-pro.com/products.json",
            429,
            "Too Many Requests",
            {"Retry-After": "60"},
            None,
        )
        self.assertEqual(scraper.retry_wait_seconds(exc, fallback=3), 60)


class TestAnimesProRow(unittest.TestCase):
    def test_sku_comes_from_product_name(self):
        card = {
            "title": AP_TITLE,
            "href": ("/collections/high-grade-hg%E6%A8%A1%E5%9E%8B"
                     "/products/hg-strike-freedom"),
            "price": "140.00",
            "compare": "178.00",
        }
        row = scraper.animes_pro_row(card)
        self.assertEqual(list(row), scraper.FIELDNAMES)
        self.assertEqual(row["sku"], JAN)
        self.assertEqual(row["price"], "140.00")
        self.assertEqual(row["regular_price"], "178.00")
        self.assertEqual(row["sell_type"], "現貨")
        self.assertEqual(
            row["url"],
            "https://animes-pro.com/products/hg-strike-freedom",
        )

    def test_grades_registered(self):
        self.assertEqual(
            set(scraper.ANIME_PRO_CATEGORIES),
            {"ap_hg", "ap_mg", "ap_rg"},
        )


if __name__ == "__main__":
    unittest.main()
