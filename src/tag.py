"""第三步：标。把新闻挂到股票池里的股票上。

先用关键词匹配，不要一上来就让模型判断——便宜、可复现、可解释。
准不准，全看 config/stocks.csv 里每只股票的关键词维护得好不好。
"""

import csv
import re
from pathlib import Path

STOCKS_PATH = Path(__file__).resolve().parent.parent / "config" / "stocks.csv"


def _split(cell: str) -> list[str]:
    return [k.strip().lower() for k in (cell or "").split(";") if k.strip()]


def load_index(path: Path = STOCKS_PATH) -> dict[str, set[str]]:
    """读股票池，构建 keyword -> {ticker} 的倒排索引。"""
    index: dict[str, set[str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue
            keywords = set(_split(row.get("keywords", "")))
            keywords.add(ticker.lower())
            name = (row.get("name") or "").strip().lower()
            if name:
                keywords.add(name)
            for kw in keywords:
                index.setdefault(kw, set()).add(ticker)
    return index


def _hit(keyword: str, text: str) -> bool:
    """英文按词边界匹配，中文按子串匹配。

    不加词边界的话，"ai" 会命中 "said"、"amd" 会命中 "amdahl"，
    一天下来你的库里全是错标。
    """
    if re.search(r"[a-z0-9]", keyword) and not re.search(r"[一-鿿]", keyword):
        return re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text) is not None
    return keyword in text


class Tagger:
    def __init__(self, stocks_path: Path = STOCKS_PATH):
        self.index = load_index(stocks_path)

    def tag(self, *texts: str) -> list[str]:
        """返回命中的 ticker 列表。打不上标不是失败——很多新闻本来就不关任何一只票。"""
        blob = " ".join(t for t in texts if t).lower()
        hits: set[str] = set()
        for keyword, tickers in self.index.items():
            if _hit(keyword, blob):
                hits |= tickers
        return sorted(hits)
