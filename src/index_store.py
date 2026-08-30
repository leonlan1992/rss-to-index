"""索引层：一张 CSV，一条新闻一行，六列。

去重靠 URL —— 已经在 index.csv 里的链接直接跳过，所以这个脚本跑十遍也只有那些行。
想换载体（Notion / 数据库），重写这一个文件就行。
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "library" / "index.csv"

COLUMNS = ["信息时间", "新闻内容", "中文翻译", "URL", "股票池关联", "入库时间"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure(path: Path = INDEX_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(COLUMNS)
    return path


def existing_urls(path: Path = INDEX_PATH) -> set[str]:
    """已经入过库的 URL。这就是去重的全部依据。"""
    ensure(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {(row.get("URL") or "").strip() for row in csv.DictReader(f)}


def append(rows: list[dict], path: Path = INDEX_PATH) -> int:
    ensure(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        for row in rows:
            writer.writerow(row)
    return len(rows)


def build_row(item: dict, title_cn: str, tickers: list[str]) -> dict:
    return {
        "信息时间": item.get("published_at") or "",
        "新闻内容": item["title_en"],
        "中文翻译": title_cn,
        "URL": item["link"],
        "股票池关联": ";".join(tickers),
        "入库时间": now_iso(),
    }


def count(path: Path = INDEX_PATH) -> int:
    ensure(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))
