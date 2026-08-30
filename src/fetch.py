"""第一步：抓。

用订阅代替搜索——源是你在 config/sources.csv 里亲手选的，
每条都带时间戳，天然增量，质量可以按源评估和淘汰。
"""

import csv
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

import feedparser

SOURCES_PATH = Path(__file__).resolve().parent.parent / "config" / "sources.csv"

# 这些参数只是投放追踪，去掉之后同一篇文章的不同链接才能被认成同一条
TRACKING_PREFIXES = ("utm_", "ref_")
TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source"}


def normalize_link(url: str) -> str:
    """URL 归一化：去掉追踪参数和末尾斜杠。去重的第一道关口。"""
    parts = urlparse(url.strip())
    kept = [(k, v) for k, v in parse_qsl(parts.query)
            if not k.lower().startswith(TRACKING_PREFIXES) and k.lower() not in TRACKING_KEYS]
    path = parts.path.rstrip("/") or "/"
    return urlunparse((parts.scheme, parts.netloc.lower(), path, "", urlencode(kept), ""))


def read_sources(path: Path = SOURCES_PATH) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f)
                if (r.get("enabled") or "").strip().lower() == "true"]


def _published(entry) -> str:
    struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", struct) if struct else ""


def fetch_source(source: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    if getattr(feed, "bozo", 0) and not feed.entries:
        raise RuntimeError(f"解析失败: {getattr(feed, 'bozo_exception', 'unknown')}")

    items = []
    for entry in feed.entries:
        link = getattr(entry, "link", None)
        title = (getattr(entry, "title", "") or "").strip()
        if link and title:
            items.append({
                "link": normalize_link(link),
                "title_en": title,
                "source": source["name"],
                "published_at": _published(entry),
            })
    return items


def fetch_all(sources: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """逐个源抓取，返回 (条目, 失败列表)。

    **单个源失败不影响其他源**——这是能安心让 cron 跑的前提。
    """
    sources = sources if sources is not None else read_sources()
    items, failures = [], []
    for source in sources:
        try:
            items.extend(fetch_source(source))
        except Exception as exc:                      # noqa: BLE001
            failures.append({"source": source["name"], "error": str(exc)})
    return items, failures
