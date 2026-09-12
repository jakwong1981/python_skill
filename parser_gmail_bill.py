import os
import base64
import re
import csv
import time
from datetime import datetime, timedelta, timezone

# 套件依賴：pip install google-api-python-client google-auth-oauthlib
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service(credentials_path="credentials.json", token_path="token.json"):
    """
    透過 OAuth 2.0 取得 Gmail API 服務物件。
    初次執行會開啟瀏覽器進行授權，後續會自 token.json 自動載入。
    """
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"找不到 '{credentials_path}'，請先由 Google Cloud Console 下載 OAuth 用戶端憑證。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def extract_body(payload):
    """
    遞迴走訪 Gmail payload 各 part 並解碼文字內文。
    """
    body_text = ""
    if 'parts' in payload:
        for part in payload['parts']:
            body_text += extract_body(part)
    else:
        mime_type = payload.get('mimeType', '')
        data = payload.get('body', {}).get('data', '')
        if data:
            decoded = base64.urlsafe_b64decode(data.encode('ASCII')).decode('utf-8', errors='ignore')
            if 'text/plain' in mime_type or ('text/html' in mime_type and not body_text):
                body_text += "\n" + decoded
    return body_text

def parse_card_info(text):
    """
    從郵件內文中識別信用卡簽賬與卡號資訊。
    """
    card_patterns = [
        r"(Visa[\s\-\•\*\.]*(?:\d{4}|[xX]{1,4}\-?\d{4}))",
        r"(Mastercard[\s\-\•\*\.]*(?:\d{4}|[xX]{1,4}\-?\d{4}))",
        r"(American\s*Express|AMEX|AE)",
        r"(銀聯|UnionPay)",
        r"(Credit\s*Card[\s\w\(\)]*)",
        r"(信用卡[\s\w\(\)]*)",
        r"(末四碼[\s\:\：]*\d{4})",
        r"(-\s*7737|\b7737\b)",
        r"(VISA\s*X\-7737)"
    ]
    for p in card_patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def parse_amount(text):
    """
    從郵件中擷取金額及貨幣單位。

    支援千位逗號（HK$1,234.56）、貨幣前置或後置（$17.33 HKD、10.80 USD）、
    中英文幣別（HKD/USD/港幣/港元/美元/港紙），以及純 $ 符號（依上下文判定幣別）。
    """
    number = r"(?<![\d.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{2})?(?![\d])"
    pairs = []  # (currency, value) 依出現順序

    def is_hkd(curr):
        return curr in ("HKD", "HK$", "港幣", "港元", "港紙")

    def is_usd(curr):
        return curr in ("USD", "US$", "美元")

    def display_curr(curr):
        if is_hkd(curr):
            return "HK$"
        if is_usd(curr):
            return "US$"
        return curr

    # 明確幣別：前綴或後綴皆可（排除「1 USD = 8.1542 HKD」之類的匯率行）
    for m in re.finditer(
        rf"(HKD|HK\$|USD|US\$|港幣|港元|港紙|美元)\s*({number})"
        rf"|({number})\s*(HKD|HK\$|USD|US\$|港幣|港元|港紙|美元)(?!\s*=)",
        text, re.IGNORECASE):
        if m.group(1):
            pairs.append((m.group(1).upper(), m.group(2).replace(",", "")))
        else:
            pairs.append((m.group(4).upper(), m.group(3).replace(",", "")))

    # 純 $ 符號：後綴標明幣別時跟隨後綴；否則歸入同信已知幣別，均無則預設美元
    for m in re.finditer(rf"(?<![A-Za-z])\$\s*({number})(?!\s*=)", text):
        val = m.group(1).replace(",", "")
        after = text[m.end():m.end() + 8]
        if re.match(r"^\s*(HKD|港幣|港元|港紙)\b", after, re.IGNORECASE):
            pairs.append(("HKD", val))
        elif pairs:
            pairs.append((pairs[0][0], val))
        else:
            pairs.append(("USD", val))

    orig_amount = ""
    hkd_amount = ""
    for curr, val in pairs:
        amt_str = f"{display_curr(curr)} {val}"
        if is_hkd(curr):
            if not hkd_amount:
                hkd_amount = val
            if not orig_amount:
                orig_amount = amt_str
        elif is_usd(curr):
            if not orig_amount:
                orig_amount = amt_str

    return orig_amount, hkd_amount

def categorize_payment(merchant, subject):
    """
    根據商戶名稱及郵件主旨分類付款類別。
    """
    m_lower = merchant.lower()
    s_lower = subject.lower()

    # 銀行轉賬
    if any(k in m_lower for k in ["shacombank", "hang seng", "hsbc", "bank", "dbs", "citi"]):
        return "銀行轉賬"
    if any(k in s_lower for k in ["payment instruction", "轉賬", "transfer", "轉數快", "fps"]):
        return "銀行轉賬"

    # 模型/玩具（P-Bandai、L Model 等）
    if "p-bandai" in m_lower or "premium bandai" in m_lower:
        return "模型/玩具"
    if "l model" in m_lower:
        return "模型/玩具"
    if any(k in s_lower for k in ["bandai", "gunpla", "模型", "gundam"]):
        return "模型/玩具"

    # API / Token 服務
    if any(k in m_lower for k in ["openrouter", "openai", "anthropic", "claude", "gemini",
                                   "google ai", "together ai", "replicate", "hugging face",
                                   "mistral", "cohere", "ai21", "perplexity", "digitalocean",
                                   "myclaw", "floatmiracle", "kiro"]):
        return "API/Token"
    if any(k in s_lower for k in ["receipt", "invoice"]) and any(k in s_lower for k in ["openrouter", "openai", "anthropic", "claude", "digitalocean", "myclaw"]):
        return "API/Token"

    # 訂閱服務/軟體
    if any(k in m_lower for k in ["netflix", "spotify", "dropbox", "notion", "figma", "slack", "microsoft"]):
        return "訂閱服務"
    if any(k in s_lower for k in ["subscription", "receipt from", "your receipt"]):
        return "訂閱服務"

    # 數位商品
    if any(k in m_lower for k in ["google play", "app store", "apple", "steam"]):
        return "數位商品"

    # 餐飲
    if any(k in m_lower for k in ["uber eats", "foodpanda", "deliveroo", "mcdonald", "kfc", "starbucks"]):
        return "餐飲"

    # 交通
    if any(k in m_lower for k in ["uber", "taxi", "grab", "mtr", "九巴"]):
        return "交通"

    # 泊車/停車場
    if any(k in m_lower for k in ["parking", "pay station", "停車場"]):
        return "泊車"
    if any(k in s_lower for k in ["parking", "pay station", "停車場"]):
        return "泊車"

    # 遊戲/娛樂（PlayStation、Steam 等）
    if any(k in m_lower for k in ["playstation", "sony", "steam", "xbox", "nintendo", "epic games"]):
        return "遊戲/娛樂"
    if any(k in s_lower for k in ["playstation", "psn", "steam store"]):
        return "遊戲/娛樂"

    # PayPal 付款
    if "paypal" in m_lower or "paypal" in s_lower:
        return "PayPal"

    # 購物/百貨
    if any(k in m_lower for k in ["twins", "donki", "don don", "aeon", "citysuper", "log-on"]):
        return "購物/百貨"

    return "其他"


def parse_receipt_url(text):
    """
    擷取收據或憑證的外部連結。
    """
    url_patterns = [
        r"https?://(?:dashboard\.)?stripe\.com/receipts/[^\s\)\"\'>]+",
        r"https?://pay\.stripe\.com/invoice/[^\s\)\"\'>]+",
        r"https?://[^\s\)\"\'>]*paypal\.com[^\s\)\"\'>]+",
        r"https?://[^\s\)\"\'>]*p-bandai\.com[^\s\)\"\'>]+",
        r"https?://[^\s\)\"\'>]*lmodel\.hk/orders/[^\s\)\"\'>]+",
        r"https?://[^\s\)\"\'>]*uber\.com[^\s\)\"\'>]+"
    ]
    for p in url_patterns:
        match = re.search(p, text)
        if match:
            return match.group(0)
    return ""

def is_pbandai_non_payment(subject, sender):
    """
    判斷是否為 Premium Bandai 的新品預購公告或出貨通知郵件（非實際付款）。
    僅對 Bandai 相關郵件生效，避免誤刪其他商戶（如 L Model 的送貨通知）。

    注意：出貨/送貨判定只看「主旨」，不看內文——訂單確認郵件的內文常提及
    shipment/出貨日期，若看內文會誤刪真正的付款郵件。
    """
    subj_lower = subject.lower()
    sender_lower = sender.lower()
    if "bandai" not in subj_lower and "bandai" not in sender_lower:
        return False
    # 新品預購公告（行銷郵件，非付款）— 僅看主旨
    if any(k in subj_lower for k in ("開始預購", "開始預訂", "開始預定", "新品預購")):
        return True
    # 出貨 / 送貨通知（非付款）— 僅看主旨
    if any(k in subj_lower for k in ("shipment", "送貨", "發貨", "出貨")):
        return True
    return False

def is_newsletter(subject):
    """
    判斷主旨是否為行銷快訊 / 電子報（非付款，如「The Twins雙子匯8月快訊」）。
    只檢查主旨，避免內文誤含關鍵字導致誤殺真實付款郵件。
    """
    subj_lower = subject.lower()
    return any(k in subj_lower for k in ("快訊", "newsletter", "電子報", "月訊"))

def is_playstation_non_payment(subject, sender):
    """
    判斷是否為 PlayStation 的行銷/推廣郵件（非實際付款）。
    僅保留主旨含「感謝您的購買」或「預購確認」的 PlayStation 郵件。
    """
    subj_lower = subject.lower()
    sender_lower = sender.lower()
    if "playstation" not in subj_lower and "playstation" not in sender_lower and "sony" not in sender_lower:
        return False
    # 僅保留實際付款郵件
    if any(k in subj_lower for k in ("感謝您的購買", "预购确认", "預購確認", "order confirmation", "receipt")):
        return False
    return True

def scan_and_generate_bill(days=45, output_csv="bill.csv"):
    service = get_gmail_service()
    
    # 動態計算時間範圍
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y/%m/%d')
    
    # 拆分多個搜尋條件，避免 Gmail API 查詢過長導致部分關鍵字失效
    queries = [
        # 主查詢：一般付款/信用卡關鍵字
        f"after:{start_date} "
        f"(credit OR card OR debit OR payment OR invoice OR receipt OR transaction OR statement "
        f"OR charged OR purchase OR subscription OR billing OR order confirmation "
        f"OR 信用卡 OR 簽賬 OR 扣款 OR 扣數 OR 結單 OR 付款 OR 交易 OR 消費 OR 訂單 OR 賬單)",
        # API / Token 服務
        f"after:{start_date} "
        f"(token OR credits OR top-up OR topup OR recharge OR usage OR quota)",
        # 特定商戶（獨立查詢確保不被遺漏）
        f"after:{start_date} (playstation OR sony OR PSN OR \"playstation store\")",
        f"after:{start_date} (paypal)",
        f"after:{start_date} (\"PREMIUM BANDAI\")",
        f"after:{start_date} (parking OR \"pay station\")",
    ]
    
    # 合併所有搜尋結果（去除重複）
    all_messages = []
    seen_msg_ids = set()
    for q in queries:
        results = service.users().messages().list(userId='me', q=q).execute()
        for m in results.get('messages', []):
            if m['id'] not in seen_msg_ids:
                seen_msg_ids.add(m['id'])
                all_messages.append(m)
        time.sleep(0.5)
    
    print(f"Gmail 搜尋結果：{len(queries)} 個查詢共找到 {len(all_messages)} 封不重複郵件")
    
    records = []
    seen_ids = set()
    debug_stats = {"total": 0, "jobsdb": 0, "pbandai": 0, "newsletter": 0, "playstation": 0, "no_amount": 0, "kept": 0}
    
    for msg_meta in all_messages:
        mid = msg_meta['id']
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        debug_stats["total"] += 1
        
        # 取得郵件內容（含重試機制以應對配額限制及連線錯誤）
        max_retries = 5
        for attempt in range(max_retries):
            try:
                msg = service.users().messages().get(userId='me', id=mid, format='full').execute()
                break
            except Exception as e:
                err_str = str(e)
                if ('rateLimitExceeded' in err_str or 'ConnectionReset' in err_str or 'Connection' in err_str) and attempt < max_retries - 1:
                    wait_time = 60 * (attempt + 1)  # 60s, 120s, 180s, 240s
                    print(f"  連線/配額錯誤，等待 {wait_time} 秒後重試 ({attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                else:
                    raise
        time.sleep(1.0)  # 避免觸發 Gmail API 配額限制
        headers = {h['name'].lower(): h['value'] for h in msg.get('payload', {}).get('headers', [])}
        
        subject = headers.get('subject', '')
        sender = headers.get('from', '')
        date_raw = headers.get('date', '')
        
        # 格式化日期為 YYYY-MM-DD
        date_str = date_raw[:16] if date_raw else ""
        try:
            parsed_dt = datetime.strptime(date_raw.split('+')[0].split('-')[0].strip(), '%a, %d %b %Y %H:%M:%S')
            date_str = parsed_dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        body = extract_body(msg.get('payload', {}))
        combined_text = f"{subject}\n{body}"
        
        # 忽略求職平台郵件（如 JobsDB 的 "job db record"）
        if "jobsdb" in combined_text.lower() or "job db" in combined_text.lower():
            debug_stats["jobsdb"] += 1
            continue
        
        # 忽略 P-Bandai 新品預購公告 / 出貨通知（非付款郵件）
        if is_pbandai_non_payment(subject, sender):
            debug_stats["pbandai"] += 1
            continue
        
        # 忽略行銷快訊 / 電子報（非付款郵件）— 只檢查主旨
        if is_newsletter(subject):
            debug_stats["newsletter"] += 1
            continue
        
        # 忽略 PlayStation 行銷/推廣郵件（僅保留「感謝您的購買」等實際付款）
        if is_playstation_non_payment(subject, sender):
            debug_stats["playstation"] += 1
            continue
        
        # 嘗試識別信用卡/支付方式（非阻斷，留空則標示「Unknown」）
        card_method = parse_card_info(combined_text) or "Unknown"
            
        orig_amount, hkd_amount = parse_amount(combined_text)
        # 若找不到 HKD 金額，則跳過不寫入 CSV
        if not hkd_amount:
            debug_stats["no_amount"] += 1
            # 印出被跳過的郵件主旨（協助除錯）
            if any(k in combined_text.lower() for k in ["playstation", "psn", "sony", "paypal"]):
                print(f"  [跳過-無HKD金額] 主旨: {subject[:60]}")
            continue
        debug_stats["kept"] += 1
        receipt_url = parse_receipt_url(combined_text)
        
        merchant = sender.split('<')[0].replace('"', '').strip()
        if not merchant or '@' in merchant:
            merchant = sender
        
        category = categorize_payment(merchant, subject)
            
        records.append({
            "Date": date_str,
            "Category": category,
            "Merchant": merchant,
            "Description": subject,
            "Amount_Original": orig_amount,
            "Amount_HKD": hkd_amount,
            "Payment_Method": card_method,
            "Email_Subject": subject,
            "Receipt_URL": receipt_url
        })
    
    # 依日期降冪排序
    records.sort(key=lambda x: x["Date"], reverse=True)
    
    # 去重：若收據連結非空且重複，僅保留最新（最前）一筆
    seen_receipts = set()
    deduped_records = []
    for r in records:
        receipt = r["Receipt_URL"]
        if receipt and receipt in seen_receipts:
            continue  # 跳過重複的收據
        if receipt:
            seen_receipts.add(receipt)
        deduped_records.append(r)
    records = deduped_records
    
    # 沒有任何含金額的交易時，不產生 CSV 檔案
    if not records:
        print("未找到任何含金額的交易，未寫入 CSV 檔案。")
        return
    
    # 寫入 CSV 檔案
    fields = ["Date", "Category", "Merchant", "Description", "Amount_Original", "Amount_HKD", "Payment_Method", "Email_Subject", "Receipt_URL"]
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow(r)
            
    print(f"成功輸出 {output_csv}，共解析出 {len(records)} 筆交易。")
    print(f"\n[除錯] 過濾統計：")
    print(f"  總郵件數: {debug_stats['total']}")
    print(f"  JobsDB 過濾: {debug_stats['jobsdb']}")
    print(f"  P-Bandai 非付款過濾: {debug_stats['pbandai']}")
    print(f"  電子報過濾: {debug_stats['newsletter']}")
    print(f"  PlayStation 行銷過濾: {debug_stats['playstation']}")
    print(f"  無金額跳過: {debug_stats['no_amount']}")
    print(f"  保留記錄: {debug_stats['kept']}")
    print()
    print_summary(records, output_csv)

def print_summary(records, csv_path):
    """
    輸出分類彙總及總金額（同時寫入 CSV 檔案尾及終端機）。
    """
    from collections import OrderedDict

    categories = OrderedDict()
    grand_total = 0.0

    for r in records:
        cat = r["Category"]
        # 優先使用 Amount_HKD，否則從 Amount_Original 提取數字
        hkd_str = r["Amount_HKD"]
        if hkd_str:
            try:
                amt = float(hkd_str)
            except ValueError:
                amt = 0.0
        else:
            # 從 Amount_Original 提取數字 (如 "HK$ 195.00" → 195.00)
            m = re.search(r"[\d]+(?:\.[\d]{2})?", r["Amount_Original"])
            amt = float(m.group()) if m else 0.0

        if cat not in categories:
            categories[cat] = {"count": 0, "total": 0.0}
        categories[cat]["count"] += 1
        categories[cat]["total"] += amt
        grand_total += amt

    # 組裝彙總文字
    lines = []
    lines.append("")
    lines.append("=" * 50)
    lines.append("付款分類彙總")
    lines.append("=" * 50)
    for cat, info in categories.items():
        lines.append(f"  {cat:　<10}  {info['count']:>2} 筆  HK$ {info['total']:>10,.2f}")
    lines.append("-" * 50)
    lines.append(f"  合計　　　　　　  {len(records):>2} 筆  HK$ {grand_total:>10,.2f}")
    lines.append("=" * 50)

    # 寫入 CSV 檔案尾
    with open(csv_path, "a", encoding="utf-8-sig") as f:
        f.write("\n".join(lines) + "\n")

    # 輸出至終端機
    print("\n".join(lines))


if __name__ == "__main__":
    scan_and_generate_bill(days=45, output_csv="bill.csv")