#!/usr/bin/env python3
"""一次性脚本：在 Notion 里把两张表建好，并把股票池填上。

    python scripts/bootstrap_notion.py            # 建表 + 用 config/stocks.csv 填股票池
    python scripts/bootstrap_notion.py --no-seed  # 只建表

跑之前需要 .env 里有 NOTION_TOKEN 和 NOTION_PARENT_PAGE_ID，
并且这个 parent page 已经 Share 给了你的 integration。
跑完把打印出来的两个 id 填回 .env。
"""

import argparse
import csv
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import os  # noqa: E402

from src.notion_sink import _post  # noqa: E402

INFO_TYPES = ["新闻", "投行报告", "专家访谈", "财报交流调研", "数据报告",
              "买方咨询报告", "Youtube", "播客", "Substack", "公众号", "书籍论文"]


def create_stock_db(parent_page_id: str) -> str:
    data = _post("/databases", {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": "股票池"}}],
        "properties": {
            "Ticker": {"title": {}},
            "公司名": {"rich_text": {}},
            "关键词": {"rich_text": {}},
        },
    })
    return data["id"]


def create_info_db(parent_page_id: str, stock_db_id: str) -> str:
    data = _post("/databases", {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"text": {"content": "信息索引"}}],
        "properties": {
            "标题": {"title": {}},
            "信息类型": {"select": {"options": [{"name": t} for t in INFO_TYPES]}},
            "信息时间": {"date": {}},
            "Source": {"rich_text": {}},
            "URL": {"url": {}},
            "原文存档": {"url": {}},
            "内容概要": {"rich_text": {}},
            "精读 Takeaway": {"rich_text": {}},
            "标签": {"multi_select": {}},
            "审阅": {"checkbox": {}},
            "股票池关联": {"relation": {"database_id": stock_db_id,
                                        "type": "dual_property",
                                        "dual_property": {}}},
        },
    })
    return data["id"]


def seed_stocks(stock_db_id: str) -> int:
    count = 0
    with open(ROOT / "config" / "stocks.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = (row.get("ticker") or "").strip()
            if not ticker:
                continue
            _post("/pages", {
                "parent": {"database_id": stock_db_id},
                "properties": {
                    "Ticker": {"title": [{"text": {"content": ticker}}]},
                    "公司名": {"rich_text": [{"text": {"content": row.get("name", "")}}]},
                    "关键词": {"rich_text": [{"text": {"content": row.get("keywords", "")[:2000]}}]},
                },
            })
            count += 1
            print(f"  + {ticker}")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-seed", action="store_true", help="不往股票池里填数据")
    args = parser.parse_args()

    parent = os.getenv("NOTION_PARENT_PAGE_ID")
    if not os.getenv("NOTION_TOKEN") or not parent:
        print("请先在 .env 里填 NOTION_TOKEN 和 NOTION_PARENT_PAGE_ID")
        return 1

    print("建「股票池」表 ...")
    stock_db_id = create_stock_db(parent)
    print(f"  id = {stock_db_id}")

    print("建「信息索引」表 ...")
    info_db_id = create_info_db(parent, stock_db_id)
    print(f"  id = {info_db_id}")

    if not args.no_seed:
        print("填股票池 ...")
        print(f"  共 {seed_stocks(stock_db_id)} 只")

    print("\n把下面两行填进 .env：\n")
    print(f"NOTION_INFO_DB_ID={info_db_id}")
    print(f"NOTION_STOCK_DB_ID={stock_db_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
