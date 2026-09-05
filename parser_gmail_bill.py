import os
import base64
import re
import csv
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
    """
    matches = re.findall(r"(HKD|\$|HK\$|USD|US\$)\s*([0-9]+(?:\.[0-9]{2})?)", text, re.IGNORECASE)
    orig_amount = ""
    hkd_amount = ""
    
    for curr, val in matches:
        amt_str = f"{curr.upper()} {val}"
        if "HK" in curr.upper():
            if not hkd_amount:
                hkd_amount = val
            if not orig_amount:
                orig_amount = amt_str
        elif "USD" in curr.upper() or "US" in curr.upper():
            if not orig_amount:
                orig_amount = amt_str

    return orig_amount, hkd_amount

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

def scan_and_generate_bill(days=30, output_csv="bill.csv"):
    service = get_gmail_service()
    
    # 動態計算時間範圍
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime('%Y/%m/%d')
    query = (
        f"after:{start_date} "
        f"(credit OR card OR debit OR payment OR invoice OR receipt OR transaction OR statement "
        f"OR 信用卡 OR 簽賬 OR 扣款 OR 扣數 OR 結單 OR 付款)"
    )
    
    print(f"正在以條件搜尋 Gmail：{query}...")
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])
    
    records = []
    seen_ids = set()
    
    for msg_meta in messages:
        mid = msg_meta['id']
        if mid in seen_ids:
            continue
        seen_ids.add(mid)
        
        msg = service.users().messages().get(userId='me', id=mid, format='full').execute()
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
            continue
        
        # 僅保留包含信用卡特徵之交易
        card_method = parse_card_info(combined_text)
        if not card_method:
            continue
            
        orig_amount, hkd_amount = parse_amount(combined_text)
        # 若信件中找不到任何金額，則跳過不寫入 CSV
        if not orig_amount and not hkd_amount:
            continue
        receipt_url = parse_receipt_url(combined_text)
        
        merchant = sender.split('<')[0].replace('"', '').strip()
        if not merchant or '@' in merchant:
            merchant = sender
            
        records.append({
            "Date": date_str,
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
    
    # 沒有任何含金額的交易時，不產生 CSV 檔案
    if not records:
        print("未找到任何含金額的交易，未寫入 CSV 檔案。")
        return
    
    # 寫入 CSV 檔案
    fields = ["Date", "Merchant", "Description", "Amount_Original", "Amount_HKD", "Payment_Method", "Email_Subject", "Receipt_URL"]
    with open(output_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow(r)
            
    print(f"成功輸出 {output_csv}，共解析出 {len(records)} 筆交易。")

if __name__ == "__main__":
    scan_and_generate_bill(days=30, output_csv="bill.csv")