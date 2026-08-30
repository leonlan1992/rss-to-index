"""索引层：一张 CSV，一条材料一行。

列名和第 3 期那张索引表完全一致，另外多一列「原标题」存英文原文，方便你核对翻译。
去重靠 URL —— 已经在 index.csv 里的链接直接跳过，所以这个脚本跑十遍也只有一行。
"""

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "library" / "index.csv"

COLUMNS = [
    "标题", "信息类型", "信息时间", "入库时间", "Source", "URL",
    "原文存档", "股票池关联", "标签", "内容概要", "精读Takeaway", "审阅", "原标题",
]


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


def build_row(item: dict, title_cn: str, tickers: list[str], tags: list[str]) -> dict:
    """把一条新闻拼成索引里的一行。空着的列是留给你自己往下做的。"""
    return {
        "标题": title_cn or item["title_en"],
        "信息类型": "新闻",
        "信息时间": item.get("published_at") or "",
        "入库时间": now_iso(),
        "Source": item.get("source") or "",
        "URL": item["link"],
        "原文存档": "",            # 抓正文入「湖」是下一步，见 README
        "股票池关联": ";".join(tickers),
        "标签": ";".join(tags),
        "内容概要": "",            # 要读正文才写得出来
        "精读Takeaway": "",        # 人读完自己填
        "审阅": "FALSE",           # 自动入库的东西默认没人看过
        "原标题": item["title_en"],
    }


def count(path: Path = INDEX_PATH) -> int:
    ensure(path)
    with open(path, newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))
