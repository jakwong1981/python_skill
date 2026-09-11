#!/usr/bin/env python3
"""Unit tests for the hourly gunpla digest (~/.hermes/scripts/hobbyland_hourly.py).

The digest script lives outside this repo (Hermes cron runs it straight from
~/.hermes/scripts/), so it is loaded here by absolute path. Only the pure
helpers are exercised — no network calls.

Run with:
    python3 test_hobbyland_digest.py -v
    pytest test_hobbyland_digest.py            # if pytest is installed
"""

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT = Path.home() / ".hermes" / "scripts" / "hobbyland_hourly.py"

spec = importlib.util.spec_from_file_location("hobbyland_hourly", SCRIPT)
digest = importlib.util.module_from_spec(spec)
sys.modules["hobbyland_hourly"] = digest
spec.loader.exec_module(digest)

# Real-world samples straight from the two shops.
HL_TITLE = "[現貨] HGUC 1/144【機動戰士高達】RGM-79C GM Type C"
AP_TITLE = "Bandai - HG 1/144 機動戰士高達 突擊自由高達極  Y2700(4573102663849)【現貨】"
JAN = "4573102663849"


def row(shop, grade, title, price, jan, rank, seed="", url=None):
    return {"shop": shop, "grade": grade, "title": title, "price": price, "jan": jan,
            "rank": rank, "seed": seed, "stock": 0,
            "url": url or f"https://example.com/{shop}/{rank}"}


class TestJanAndTitles(unittest.TestCase):
    def test_jan_extracted_from_animes_pro_title(self):
        self.assertEqual(digest._jan_of(AP_TITLE), JAN)
        self.assertEqual(digest._jan_of(HL_TITLE), "")

    def test_jan_ignores_shorter_or_longer_digit_runs(self):
        self.assertEqual(digest._jan_of("Y2700 45731026638490"), "")   # 14 digits
        self.assertEqual(digest._jan_of("code 1234567890123"), "")     # not a 4-prefix

    def test_hobbyland_pic_month_becomes_seed_date(self):
        seed = digest._pic_month("storage/2026/09/4573102591630-6573698638.webp")
        self.assertEqual(seed, "2026-09-01T00:00:00")
        self.assertEqual(digest._pic_month(""), "")

    def test_clean_title_strips_noise(self):
        cleaned = digest.clean_title(AP_TITLE)
        self.assertNotIn(JAN, cleaned)
        self.assertNotIn("Bandai", cleaned)
        self.assertNotIn("【現貨】", cleaned)
        self.assertTrue(cleaned.startswith("HG 1/144"))

    def test_clean_title_unescapes_entities_and_caps_length(self):
        self.assertNotIn("&nbsp;", digest.clean_title("MG 1/100 V衝擊高達 Ver.Ka&nbsp;"))
        self.assertLessEqual(len(digest.clean_title("x" * 200)), digest.TITLE_MAX)


class TestGunplaFilter(unittest.TestCase):
    def test_keeps_grade_kits(self):
        for title, grade in ((HL_TITLE, "HG"), ("Bandai MG 1/100 完美高達 Y4400", "MG"),
                             ("MGSD【水星的魔女】風靈高達", "MG"),
                             ("RG 1/144 043 飛翼高達零式 Y4200", "RG"),
                             ("Bandai - 1/100 MG 全裝甲型高達 Ver.Ka", "MG")):
            self.assertTrue(digest.looks_like_gunpla(title, grade), title)

    def test_drops_figure_and_preorder_noise(self):
        # these really do sit in animes-pro's "MG模型" collection
        for title in ("Tamashii Art 魂商店 PVC 龍珠 孫悟空與龍Y25000",
                      "【預訂日期至06-Sep-26】Planet-X - Ultraman Taro - Gold Chrome Version",
                      "[Jumbo Machineder] 巨靈神 Y22000",
                      "Alphamax -《銀河戰國群雄傳》戰艦金剛II (AX-0319) Y22000"):
            self.assertFalse(digest.looks_like_gunpla(title, "MG"), title)

    def test_keeps_unnamed_kit_with_scale_and_gundam_word(self):
        self.assertTrue(digest.looks_like_gunpla("Bandai 1/144 高達 特別版", "HG"))


class TestCrossShopMatch(unittest.TestCase):
    def test_same_jan_collapses_to_the_cheaper_shop(self):
        rows = [row(digest.SHOP_HL, "HG", HL_TITLE, 138.0, "4573102591456", 1),
                row(digest.SHOP_AP, "HG", AP_TITLE, 104.0, "4573102591456", 2)]
        merged = digest.match_across_shops(rows)
        self.assertEqual(len(merged), 1)
        best = merged[0]
        self.assertEqual(best["price"], 104.0)
        self.assertEqual(best["shop"], digest.SHOP_AP)
        self.assertEqual(best["alt"], {"shop": digest.SHOP_HL, "price": 138.0})
        self.assertEqual(len(best["urls"]), 2)

    def test_hobbyland_wins_when_cheaper(self):
        rows = [row(digest.SHOP_AP, "RG", "RG 025 1/144 獨角獸高達", 258.0, "4573102616098", 1),
                row(digest.SHOP_HL, "RG", "RG 025 1/144【機動戰士高達UC】RX-0 獨角獸高達",
                    198.0, "4573102616098", 2)]
        merged = digest.match_across_shops(rows)
        self.assertEqual(merged[0]["shop"], digest.SHOP_HL)
        self.assertEqual(merged[0]["price"], 198.0)
        self.assertEqual(merged[0]["alt"]["shop"], digest.SHOP_AP)

    def test_items_without_a_jan_are_never_merged(self):
        rows = [row(digest.SHOP_HL, "MG", "MG 1/100 限定 A", 300.0, "", 1),
                row(digest.SHOP_HL, "MG", "MG 1/100 限定 B", 310.0, "", 2)]
        self.assertEqual(len(digest.match_across_shops(rows)), 2)

    def test_same_jan_in_different_grades_stays_separate(self):
        rows = [row(digest.SHOP_HL, "HG", "kit", 100.0, JAN, 1),
                row(digest.SHOP_AP, "MG", "kit", 90.0, JAN, 1)]
        self.assertEqual(len(digest.match_across_shops(rows)), 2)


class TestNewestSelection(unittest.TestCase):
    def test_top20_is_newest_first_and_capped(self):
        now = datetime(2026, 9, 11, 13, 0)
        entries = [dict(row(digest.SHOP_HL, "HG", f"kit {i}", 100.0, "", i),
                        first_seen=(now - timedelta(days=i)).strftime(digest.ISO_FMT))
                   for i in range(30)]
        picked = digest.newest(entries)
        self.assertEqual(len(picked), digest.TOP_N)
        self.assertEqual(picked[0]["title"], "kit 0")           # newest
        self.assertNotIn("kit 20", [e["title"] for e in picked])

    def test_shop_listing_order_breaks_ties_within_a_month(self):
        entries = [dict(row(digest.SHOP_HL, "HG", f"rank{r}", 100.0, "", r),
                        first_seen="2026-09-01T00:00:00") for r in (3, 1, 2)]
        picked = digest.newest(entries)
        self.assertEqual([e["title"] for e in picked], ["rank1", "rank2", "rank3"])

    def test_first_seen_is_kept_and_seed_is_used_only_once(self):
        entry = dict(row(digest.SHOP_HL, "HG", "kit", 100.0, JAN, 1,
                         seed="2026-09-01T00:00:00"), urls=["u1"])
        old = {"u1": {"first_seen": "2026-08-15T09:00:00"}}
        merged = digest.apply_first_seen([entry], old)
        self.assertEqual(merged[0]["first_seen"], "2026-08-15T09:00:00")

        fresh = dict(entry, urls=["u2"])          # an unseen URL falls back to seed
        merged = digest.apply_first_seen([fresh], old)
        self.assertEqual(merged[0]["first_seen"], "2026-09-01T00:00:00")

    def test_timezone_aware_and_naive_stamps_compare(self):
        # animes-pro sends +08:00, Hobbyland sends naive dates
        entries = [dict(row(digest.SHOP_HL, "HG", "naive", 1.0, "", 1, seed="2026-09-01T00:00:00"),
                        urls=["a"]),
                   dict(row(digest.SHOP_AP, "HG", "aware", 1.0, "", 2,
                            seed="2026-09-10T17:28:32+08:00"), urls=["b"])]
        merged = digest.apply_first_seen(entries, {})
        self.assertEqual(merged[1]["first_seen"], "2026-09-10T17:28:32")
        self.assertEqual(digest.newest(merged)[0]["title"], "aware")

    def test_is_new_uses_a_24_hour_window(self):
        now = datetime(2026, 9, 11, 13, 0)
        recent = {"first_seen": (now - timedelta(hours=3)).strftime(digest.ISO_FMT)}
        old = {"first_seen": (now - timedelta(hours=30)).strftime(digest.ISO_FMT)}
        self.assertTrue(digest.is_new(recent, now))
        self.assertFalse(digest.is_new(old, now))


class TestMessageLayout(unittest.TestCase):
    def _selected(self):
        rows = [row(digest.SHOP_HL, "HG", HL_TITLE, 108.0, "4573102591630", 1,
                    seed="2026-09-01T00:00:00"),
                row(digest.SHOP_AP, "HG", AP_TITLE, 178.0, JAN, 2,
                    seed="2026-09-10T00:00:00")]
        merged = digest.apply_first_seen(digest.match_across_shops(rows), {})
        now = datetime(2026, 9, 11, 13, 0)
        return {"HG": [(e, digest.is_new(e, now)) for e in merged],
                "MG": [], "RG": []}, now

    def test_english_block_comes_first_then_chinese(self):
        selected, now = self._selected()
        message = digest.build_message(selected, {"HG": 2}, 2, now)
        english_at = message.index("GUNPLA PRICE WATCH")
        chinese_at = message.index("高達模型價格監察")
        self.assertLess(english_at, chinese_at)
        self.assertIn("🆕", message)                      # the fresh animes-pro kit
        self.assertIn("[Hobbyland]", message)
        self.assertIn("[animes-pro]", message)

    def test_bilingual_message_drops_chinese_block_when_over_budget(self):
        selected, now = self._selected()
        full = digest.build_message(selected, {"HG": 2}, 2, now,
                                    budget=digest.EXPRESS_DEFAULT_BUDGET)
        squeezed = digest.build_message(selected, {"HG": 2}, 2, now, budget=400)
        self.assertIn("高達模型價格監察", full)
        self.assertNotIn("高達模型價格監察", squeezed)
        self.assertIn("Chinese block omitted", squeezed)
        self.assertIn("GUNPLA PRICE WATCH", squeezed)

    def test_alt_shop_price_is_shown_only_when_matched(self):
        rows = [row(digest.SHOP_AP, "RG", "RG 025 1/144 獨角獸高達", 258.0, "4573102616098", 1),
                row(digest.SHOP_HL, "RG", "RG 025 1/144【獨角獸高達】", 198.0, "4573102616098", 2)]
        merged = digest.apply_first_seen(digest.match_across_shops(rows), {})
        now = datetime(2026, 9, 11, 13, 0)
        message = digest.build_message({"HG": [], "MG": [], "RG": [(merged[0], False)]},
                                       {"RG": 1}, 2, now)
        self.assertIn("HK$198", message)
        self.assertIn("animes-pro HK$258", message)

    def test_real_message_stays_inside_the_bridge_budget(self):
        selected, now = self._selected()
        message = digest.build_message(selected, {"HG": 2}, 2, now)
        self.assertLess(digest.payload_bytes(message), digest.bridge_body_budget())


if __name__ == "__main__":
    unittest.main(verbosity=2)
