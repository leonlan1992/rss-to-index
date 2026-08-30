"""第三步：标。

先用关键词匹配，不要一上来就让模型判断——便宜、可复现、可解释。
拿不准的少数情况再交给模型，那是后话。
"""

import csv
import re
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _split(cell: str) -> list[str]:
    return [k.strip().lower() for k in (cell or "").split(";") if k.strip()]


def load_index(path: Path, key_col: str) -> dict[str, set[str]]:
    """读 csv，构建 keyword -> {key} 的倒排索引。"""
    index: dict[str, set[str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row.get(key_col) or "").strip()
            if not key:
                continue
            keywords = set(_split(row.get("keywords", "")))
            keywords.add(key.lower())
            name = (row.get("name") or "").strip().lower()
            if name:
                keywords.add(name)
            for kw in keywords:
                index.setdefault(kw, set()).add(key)
    return index


def _hit(keyword: str, text: str) -> bool:
    """英文按词边界匹配，中文按子串匹配。

    不加词边界的话，"ai" 会命中 "said"、"amd" 会命中 "amdahl"，
    一天下来你的库里全是错标。
    """
    if re.search(r"[a-z0-9]", keyword) and not re.search(r"[一-鿿]", keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


def match(text: str, index: dict[str, set[str]]) -> list[str]:
    text = (text or "").lower()
    hits: set[str] = set()
    for keyword, keys in index.items():
        if _hit(keyword, text):
            hits |= keys
    return sorted(hits)


class Tagger:
    def __init__(self, stocks_path: Path | None = None, topics_path: Path | None = None):
        self.stocks = load_index(stocks_path or CONFIG_DIR / "stocks.csv", "ticker")
        self.topics = load_index(topics_path or CONFIG_DIR / "topics.csv", "tag")

    def tag(self, *texts: str) -> tuple[list[str], list[str]]:
        blob = " ".join(t for t in texts if t)
        return match(blob, self.stocks), match(blob, self.topics)


def tag_pending(conn, tagger: Tagger, limit: int | None = None) -> dict:
    """给未处理的条目打股票和主题标签。

    打不上标不是失败——很多新闻本来就不关任何一只票。
    强行挂一个标签，比留空更糟。
    """
    from . import db

    rows = db.unprocessed(conn, limit)
    tagged = 0
    for row in rows:
        tickers, tags = tagger.tag(row["title_en"], row["title_cn"])
        db.update_item(conn, row["id"], tickers=tickers, tags=tags)
        if tickers:
            tagged += 1
    return {"scanned": len(rows), "with_ticker": tagged}
