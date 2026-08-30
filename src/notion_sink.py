"""第四步：存。

写进 Notion 的信息索引表，并用 relation 挂到股票池表上。

这一步最容易绊倒人的地方：**relation 字段要的是 page id，不是 ticker。**
所以写之前得先把股票池整张表拉下来，在内存里建 ticker -> page_id 的映射。
成本在这儿，收益也在这儿——存的是 id 而不是字符串，公司那一侧才能反查。
"""

import os

import requests

from . import db

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"   # 固定版本，免得哪天 API 变了脚本莫名其妙挂掉


def _headers(token: str | None = None) -> dict:
    return {
        "Authorization": f"Bearer {token or os.environ['NOTION_TOKEN']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _post(path: str, payload: dict, token: str | None = None) -> dict:
    resp = requests.post(f"{API}{path}", headers=_headers(token), json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Notion {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def query_all(database_id: str, token: str | None = None) -> list[dict]:
    """把一张表整个拉下来（自动翻页）。"""
    pages, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        data = _post(f"/databases/{database_id}/query", payload, token)
        pages.extend(data["results"])
        if not data.get("has_more"):
            return pages
        cursor = data["next_cursor"]


def _plain(prop: dict) -> str:
    kind = prop.get("type")
    parts = prop.get(kind) or []
    if kind in ("title", "rich_text"):
        return "".join(p.get("plain_text", "") for p in parts).strip()
    return ""


def build_ticker_map(stock_db_id: str, token: str | None = None) -> dict[str, str]:
    """ticker -> notion page id。写 relation 之前必须先有它。"""
    mapping = {}
    for page in query_all(stock_db_id, token):
        for prop in page["properties"].values():
            if prop.get("type") == "title":
                ticker = _plain(prop)
                if ticker:
                    mapping[ticker.upper()] = page["id"]
                break
    return mapping


def build_properties(row, ticker_map: dict[str, str]) -> dict:
    title = row["title_cn"] or row["title_en"]
    props: dict = {
        "标题": {"title": [{"text": {"content": title[:2000]}}]},
        "信息类型": {"select": {"name": "新闻"}},
        "Source": {"rich_text": [{"text": {"content": (row["source"] or "")[:2000]}}]},
        "URL": {"url": row["link"] or None},
        "审阅": {"checkbox": False},          # 自动入库的东西默认没人看过
    }
    if row["published_at"]:
        props["信息时间"] = {"date": {"start": row["published_at"]}}

    tickers = db.loads(row["tickers"])
    relations = [{"id": ticker_map[t.upper()]} for t in tickers if t.upper() in ticker_map]
    if relations:
        props["股票池关联"] = {"relation": relations}

    tags = db.loads(row["tags"])
    if tags:
        props["标签"] = {"multi_select": [{"name": t} for t in tags]}
    return props


def create_page(info_db_id: str, row, ticker_map: dict[str, str], token: str | None = None) -> str:
    data = _post("/pages", {
        "parent": {"database_id": info_db_id},
        "properties": build_properties(row, ticker_map),
    }, token)
    return data["id"]


def push_pending(conn, info_db_id: str, stock_db_id: str,
                 limit: int | None = None, token: str | None = None) -> dict:
    """把未处理的条目写进 Notion。

    顺序纪律：**先写 Notion，成功之后再回写 processed=1 和 page id。**
    反过来的话，中途崩一次就会留下"暂存表说处理过、Notion 里却没有"的幽灵记录。
    """
    ticker_map = build_ticker_map(stock_db_id, token)
    rows = db.unprocessed(conn, limit)
    pushed, failures = 0, []
    for row in rows:
        try:
            page_id = create_page(info_db_id, row, ticker_map, token)
            db.mark_processed(conn, row["id"], page_id)
            pushed += 1
        except Exception as exc:                      # noqa: BLE001
            failures.append({"id": row["id"], "title": row["title_en"][:60], "error": str(exc)})
    return {"pushed": pushed, "failures": failures, "stock_map_size": len(ticker_map)}
