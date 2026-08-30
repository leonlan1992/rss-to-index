"""SQLite 暂存层。

抓下来的条目先落这里，处理完再标记 processed。
这张表就是文章里 update/ 目录的数据库版：processed=0 ＝ 还没建索引的材料。

想换成 Supabase / Postgres，只需要重写这一个文件。
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "items.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    link           TEXT NOT NULL UNIQUE,   -- 去重依据：归一化之后的 URL
    title_en       TEXT NOT NULL,
    source         TEXT,
    published_at   TEXT,
    title_cn       TEXT,
    tickers        TEXT,                   -- JSON 数组
    tags           TEXT,                   -- JSON 数组
    notion_page_id TEXT,
    processed      INTEGER NOT NULL DEFAULT 0,
    processed_at   TEXT,
    created_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_processed ON items(processed);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_item(conn: sqlite3.Connection, item: dict) -> bool:
    """插入一条。link 已存在就跳过，返回 False。

    这就是幂等的全部秘密：唯一约束 + INSERT OR IGNORE。
    同一条新闻抓十遍，库里还是一行。
    """
    cur = conn.execute(
        """INSERT OR IGNORE INTO items (link, title_en, source, published_at, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (item["link"], item["title_en"], item.get("source"),
         item.get("published_at"), now_iso()),
    )
    conn.commit()
    return cur.rowcount > 0


def unprocessed(conn: sqlite3.Connection, limit: int | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM items WHERE processed = 0 ORDER BY published_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql).fetchall()


def update_item(conn: sqlite3.Connection, item_id: int, **fields) -> None:
    if not fields:
        return
    for key in ("tickers", "tags"):
        if key in fields and not isinstance(fields[key], str):
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE items SET {assignments} WHERE id = ?",
                 (*fields.values(), item_id))
    conn.commit()


def mark_processed(conn: sqlite3.Connection, item_id: int, notion_page_id: str) -> None:
    update_item(conn, item_id,
                notion_page_id=notion_page_id, processed=1, processed_at=now_iso())


def loads(value) -> list:
    """tickers / tags 字段存的是 JSON 文本，读出来统一成 list。"""
    if not value:
        return []
    if isinstance(value, list):
        return value
    return json.loads(value)


def counts(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN processed = 1 THEN 1 ELSE 0 END) AS done,
                  SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) AS pending
           FROM items"""
    ).fetchone()
    return {"total": row["total"], "done": row["done"] or 0, "pending": row["pending"] or 0}
