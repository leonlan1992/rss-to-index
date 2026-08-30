"""把四步串起来，并且把每一步的数字记下来。

定时任务的难点从来不是"怎么定时"，是"它失败了你不知道"。
所以这里做三件事：留日志、统计每步数字、结果异常时返回非零退出码。
"""

import logging
import os
from pathlib import Path

from . import db, fetch, notion_sink, tag, translate

LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "run.log"


def setup_logging(verbose: bool = True) -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pipeline")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    if verbose:
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        logger.addHandler(stream)
    return logger


def run(limit: int | None = None, dry_run: bool = False, verbose: bool = True) -> dict:
    log = setup_logging(verbose)
    conn = db.connect()
    stats: dict = {}

    log.info("=" * 60)

    # 1. 抓
    stats["fetch"] = fetch.fetch_all(conn)
    log.info("抓取：看到 %d 条，新增 %d 条", stats["fetch"]["seen"], stats["fetch"]["added"])
    for failure in stats["fetch"]["failures"]:
        log.error("源失败 %s: %s", failure["source"], failure["error"])

    pending = db.unprocessed(conn, limit)
    log.info("待处理：%d 条", len(pending))
    if not pending:
        log.info("没有新东西，收工")
        return stats

    # 2. 翻
    if dry_run:
        log.info("翻译：dry-run 跳过")
        stats["translate"] = {"translated": 0, "failures": [], "skipped": True}
    else:
        stats["translate"] = translate.translate_pending(conn, translate.Translator(), limit)
        log.info("翻译：%d 条", stats["translate"]["translated"])
        for failure in stats["translate"]["failures"]:
            log.error("翻译失败 id=%s: %s", failure["id"], failure["error"])

    # 3. 标（本地关键词匹配，不花钱，dry-run 也照跑）
    stats["tag"] = tag.tag_pending(conn, tag.Tagger(), limit)
    log.info("打标：扫了 %d 条，其中 %d 条挂上了股票",
             stats["tag"]["scanned"], stats["tag"]["with_ticker"])

    # 4. 存
    if dry_run:
        log.info("写入 Notion：dry-run 跳过")
        stats["notion"] = {"pushed": 0, "failures": [], "skipped": True}
    else:
        stats["notion"] = notion_sink.push_pending(
            conn, os.environ["NOTION_INFO_DB_ID"], os.environ["NOTION_STOCK_DB_ID"], limit)
        log.info("写入 Notion：%d 条（股票池映射 %d 只）",
                 stats["notion"]["pushed"], stats["notion"]["stock_map_size"])
        for failure in stats["notion"]["failures"]:
            log.error("写入失败 id=%s %s: %s", failure["id"], failure["title"], failure["error"])

    stats["db"] = db.counts(conn)
    log.info("库存：共 %d 条，已处理 %d，待处理 %d",
             stats["db"]["total"], stats["db"]["done"], stats["db"]["pending"])
    return stats


def had_failures(stats: dict) -> bool:
    """有任何一步失败就返回 True——留给 cron 判断要不要告警。"""
    return any(stats.get(step, {}).get("failures") for step in ("fetch", "translate", "notion"))
