#!/usr/bin/env python3
"""Task difficulty router.

Usage:
    python3 task_router.py
    python3 task_router.py --task "refactor the auth module" --json
    python3 task_router.py --task - --json   # read the task from stdin

互動式腳本：輸入任務內容後，呼叫 judge (jev) 模型判斷任務難度
(hard / medium / easy)，再 echo 對應的路由模型：

    easy   -> deepseek / qwen
    medium -> kimi / grok / gemini
    hard   -> claude code / chatgpt

非互動模式印 Hermes `/model` 指令（與上面的人類標籤分開）：

    easy   -> /model deepseek
    medium -> /model grok
    hard   -> /model opencode-zen:claude-opus-5-5

Judge 模型走 OpenRouter 的 decisions API（設定方式同 testjev.py）：

    OPENROUTER_API_KEY   放在 .env 或 export（未設定時退回本地關鍵字 heuristic）
    JEV_MODEL            預設 ~typesafe/jev-latest

只依賴標準函式庫，無需 pip install。
"""

import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

JEV_API_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = os.environ.get("JEV_MODEL", "~typesafe/jev-latest")
REQUEST_TIMEOUT = 30

ROUTES = {
    "easy": ["deepseek", "qwen"],
    "medium": ["kimi", "grok", "gemini"],
    "hard": ["claude code", "chatgpt"],
}

# Hermes /model targets. Primary is index 0. Not the same as ROUTES labels.
# hard is provider:model — opencode-zen is a provider, not a built-in model alias.
MODEL_ALIASES = {
    "easy": ["deepseek", "qwen"],
    "medium": ["grok", "kimi", "gemini"],
    "hard": ["opencode-zen:claude-opus-5-5"],
}

HARD_KEYWORDS = (
    "architecture", "設計", "重構", "refactor", "distributed", "分散式",
    "optimize performance", "效能", "algorithm", "演算法", "from scratch",
    "整個", "migrate", "遷移", "security audit",
)
MEDIUM_KEYWORDS = (
    "debug", "修", "bug", "feature", "功能", "api", "script", "腳本",
    "test", "測試", "implement", "實作", "寫一個", "scraper", "爬",
)


def load_env(path=".env"):
    """極簡 .env 載入器（KEY=VALUE，每行一筆），避免額外依賴 python-dotenv。"""
    env_file = Path(path)
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def classify_with_jev(task: str) -> str:
    """Call the judge (jev) decisions API; returns easy|medium|hard."""
    payload = {
        "model": JEV_MODEL,
        "state": task,
        "questions": {
            "difficulty": {
                "type": "choice",
                "instructions": "How difficult is this task for an LLM to complete?",
                "criteria": {
                    "easy": "Simple lookup, formatting, short snippet, boilerplate, trivial Q&A",
                    "medium": "Multi-step coding, moderate reasoning, debugging, small features",
                    "hard": "Architecture design, complex algorithms, large refactors, deep reasoning",
                },
            }
        },
    }
    req = urllib.request.Request(
        JEV_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if "answers" not in data:
        raise ValueError(f"API error: {data}")
    answer = data["answers"]["difficulty"]["choice"]
    if answer not in ROUTES:
        raise ValueError(f"judge model 回傳無法解析: {answer!r}")
    return answer


def classify_with_heuristic(task: str) -> str:
    """離線 fallback：用關鍵字粗略判斷難度。"""
    text = task.lower()
    if any(k in text for k in HARD_KEYWORDS):
        return "hard"
    if any(k in text for k in MEDIUM_KEYWORDS) or len(task) > 200:
        return "medium"
    return "easy"


def classify(task: str) -> tuple[str, str]:
    """回傳 (level, source)，source 標記是 jev 模型還是 heuristic。"""
    load_env()
    if os.environ.get("JEV_DISABLE") == "1":
        return classify_with_heuristic(task), "local heuristic (JEV_DISABLE=1)"
    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            return classify_with_jev(task), f"jev model ({JEV_MODEL})"
        except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError, TimeoutError) as e:
            # Do not include request headers in this message — URLError reason is enough.
            print(f"[warn] jev model 呼叫失敗，改用 heuristic: {e}", file=sys.stderr)
    return classify_with_heuristic(task), "local heuristic (未設定 OPENROUTER_API_KEY)"


def route_payload(task: str) -> dict:
    level, source = classify(task)
    aliases = MODEL_ALIASES[level]
    return {
        "level": level,
        "source": source,
        "alias": aliases[0],
        "alternates": aliases[1:],
        "labels": ROUTES[level],
        "command": f"/model {aliases[0]}",
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Classify a task and print the Hermes /model alias.")
    parser.add_argument("--task", help="Task text. Use - to read stdin. Omit for interactive prompt.")
    parser.add_argument("--json", action="store_true", help="Print a single JSON object to stdout.")
    args = parser.parse_args()

    if args.task is None:
        try:
            task = input("請輸入任務內容: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return
    elif args.task == "-":
        task = sys.stdin.read().strip()
    else:
        task = args.task.strip()

    if not task:
        print("任務內容不可為空。", file=sys.stderr)
        raise SystemExit(2)

    payload = route_payload(task)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"難度判定: {payload['level']}  (by {payload['source']})")
    print(f"route to {' / '.join(payload['labels'])}")
    print(f"建議指令: {payload['command']}")


if __name__ == "__main__":
    main()
